"""Sign-in through the accounts service.

accounts.adverserial.ai is where people create an account, sign in, pass their second step and
reset a password. This chat keeps its own session cookie, and trusts the accounts service for
exactly two things, each proven by a short-lived Ed25519 signature made with a key only that
service holds (this chat holds the public half and nothing else):

* a *handoff*: "this browser has just finished signing in as this account". The browser carries
  it here in a form body, once, and gets this chat's own session cookie in return;
* a *call*: the accounts service itself asking this chat to check a password, create an account,
  link a Google identity, or end an account's chat sessions. A call is bound to the exact request
  body and to one action, and is accepted once.

Nothing here reads request input except through the functions below, and every one of them fails
closed. This module imports only the standard library and PyJWT so it can be tested on its own.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time

import jwt

HANDOFF_TYPE = 'adverserial-chat-accounts-handoff/v1'
CALL_TYPE = 'adverserial-chat-accounts-call/v1'
ACTIONS = frozenset({'signin', 'provision', 'link', 'revoke'})
CALL_HEADER = 'x-accounts-assertion'
MAX_LIFETIME = 60          # seconds an assertion may live, at most
MAX_TOKEN = 4096
MAX_BODY = 16384
_USER_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z', re.ASCII)
_JTI = re.compile(r'[A-Za-z0-9_-]{16,128}\Z', re.ASCII)
_HTTPS_ORIGIN = re.compile(r'https://[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?(?::[0-9]{1,5})?\Z', re.ASCII)
_memory_seen: dict[str, int] = {}


class Refused(Exception):
    """A request this module will not act on. Carries the HTTP answer, never a reason an attacker could use."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def accounts_origin() -> str:
    """The one site allowed to send a handoff. Always HTTPS; anything else switches the feature off."""
    value = os.getenv('ACCOUNTS_GATEWAY_ORIGIN', 'https://accounts.adverserial.ai').strip().rstrip('/').lower()
    return value if _HTTPS_ORIGIN.fullmatch(value) else ''


def chat_origin() -> str:
    domain = os.getenv('CHAT_DOMAIN', 'chat.adverserial.ai').strip().lower().rstrip('/')
    value = f'https://{domain}'
    return value if _HTTPS_ORIGIN.fullmatch(value) else ''


def keys() -> dict:
    """Public keys trusted to sign for the accounts service, by key id. Empty when not configured."""
    try:
        listed = json.loads(os.getenv('ACCOUNTS_GATEWAY_JWKS_JSON', '') or '{}').get('keys', [])
        return {
            k['kid']: jwt.algorithms.OKPAlgorithm.from_jwk(json.dumps({'kty': 'OKP', 'crv': 'Ed25519', 'x': k['x']}))
            for k in listed
            if isinstance(k, dict)
            and k.get('kty') == 'OKP'
            and k.get('crv') == 'Ed25519'
            and isinstance(k.get('kid'), str)
            and isinstance(k.get('x'), str)
            and 'd' not in k  # a private key has no business in this setting
        }
    except (ValueError, TypeError, KeyError, AttributeError, jwt.PyJWTError):
        return {}


def configured() -> bool:
    """True when this chat can verify the accounts service at all."""
    return bool(keys()) and bool(accounts_origin()) and bool(chat_origin())


def enforced() -> bool:
    """True when the accounts service is the only way in: this chat's own sign-in, sign-up,
    password change and Google login then answer nobody but that service.

    The switch alone decides. If the key or an address is missing or malformed while the switch
    is on, nothing can be verified and every guarded route refuses: a broken setting must close
    sign-in, never quietly reopen the old way in.
    """
    return os.getenv('ACCOUNTS_GATEWAY', '').strip().lower() in {'1', 'true', 'yes', 'on'}


def misconfigured() -> bool:
    """The switch is on but nothing can be verified. Sign-in is closed until this is fixed."""
    return enforced() and not configured()


def bounded_length(request) -> None:
    """Refuse a body that is too large, or of unknown size, before any of it is read."""
    length = _header(request, 'content-length')
    if not length.isdecimal():
        raise Refused(411, 'Length required.')
    if int(length) > MAX_BODY:
        raise Refused(413, 'Request too large.')


def _claims(token, expected_type: str) -> dict:
    if not configured():
        raise Refused(503, 'Sign-in through your account is not configured.')
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN:
        raise Refused(401, 'Invalid or expired sign-in.')
    try:
        header = jwt.get_unverified_header(token)
        key = keys().get(header.get('kid')) if header.get('alg') == 'EdDSA' else None
        if key is None:
            raise ValueError('unknown key')
        claims = jwt.decode(
            token,
            key,
            algorithms=['EdDSA'],
            audience=chat_origin(),
            issuer=accounts_origin(),
            leeway=5,
            options={'require': ['exp', 'iat', 'jti', 'iss', 'aud']},
        )
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError):
        raise Refused(401, 'Invalid or expired sign-in.') from None
    jti, issued, expires = claims.get('jti'), claims.get('iat'), claims.get('exp')
    if (
        claims.get('typ') != expected_type
        or not isinstance(jti, str)
        or not _JTI.fullmatch(jti)
        or type(issued) is not int
        or type(expires) is not int
        or not 0 < expires - issued <= MAX_LIFETIME
        or issued > int(time.time()) + 5
    ):
        raise Refused(401, 'Invalid or expired sign-in.')
    return claims


def verify_handoff(token) -> dict:
    """The verified handoff: {'uid', 'email', 'jti', 'exp'}. Raises Refused otherwise."""
    claims = _claims(token, HANDOFF_TYPE)
    uid, email = claims.get('uid'), claims.get('sub')
    if not isinstance(uid, str) or not _USER_ID.fullmatch(uid) or not isinstance(email, str) or not 3 <= len(email) <= 254:
        raise Refused(401, 'Invalid or expired sign-in.')
    return {'uid': uid, 'email': email, 'jti': claims['jti'], 'exp': claims['exp']}


def verify_call(token, action: str, body: bytes) -> dict:
    """A verified call from the accounts service for exactly this action and exactly this body."""
    if action not in ACTIONS:
        raise Refused(404, 'Not found.')
    claims = _claims(token, CALL_TYPE)
    digest = hashlib.sha256(body).hexdigest()
    sent = claims.get('req')
    # Compare as bytes of equal length; both are lowercase hex of a public hash, so timing says nothing.
    if claims.get('act') != action or not isinstance(sent, str) or sent != digest:
        raise Refused(401, 'Invalid or expired sign-in.')
    return {'jti': claims['jti'], 'exp': claims['exp']}


async def consume(redis, prefix: str, jti: str, expires: int) -> None:
    """Accept an assertion once. A second use, or a store that cannot say, is refused."""
    ttl = max(1, int(expires) - int(time.time()) + 10)
    name = f'{prefix}:accounts-gateway:used:{hashlib.sha256(jti.encode()).hexdigest()}'
    if redis is not None:
        try:
            fresh = await redis.set(name, '1', nx=True, ex=ttl)
        except Exception:
            raise Refused(503, 'Sign-in is temporarily unavailable.') from None
        if not fresh:
            raise Refused(409, 'This sign-in was already used.')
        return
    # Without a shared store, one process can still remember what it has seen. Several processes
    # cannot, so a hosted deployment (which runs several) must have the shared store.
    if os.getenv('DYNO') or os.getenv('ACCOUNTS_GATEWAY_REQUIRE_SHARED_STORE', '') == '1':
        raise Refused(503, 'Sign-in is temporarily unavailable.')
    now = int(time.time())
    for old in [key for key, until in _memory_seen.items() if until < now]:
        del _memory_seen[old]
    if name in _memory_seen:
        raise Refused(409, 'This sign-in was already used.')
    _memory_seen[name] = now + ttl


def _header(request, name: str) -> str:
    return request.headers.get(name, '')


async def server_call(request, action: str, prefix: str) -> bytes:
    """Admit one call from the accounts service and return its body.

    A browser can never make this request: it must carry no Origin, no cookie and no Fetch
    Metadata, and a signature over this exact body that no browser holds.
    """
    if _header(request, 'origin') or _header(request, 'cookie') or _header(request, 'sec-fetch-site'):
        raise Refused(403, 'Not available to browsers.')
    bounded_length(request)
    body = await request.body()
    if len(body) > MAX_BODY:
        raise Refused(413, 'Request too large.')
    verified = verify_call(_header(request, CALL_HEADER), action, body)
    await consume(getattr(request.app.state, 'redis', None), prefix, verified['jti'], verified['exp'])
    return body


def browser_handoff_origin_ok(request) -> bool:
    """The handoff form is posted by the accounts site, and by no other."""
    origin = _header(request, 'origin').strip().rstrip('/').lower()
    return bool(origin) and origin == accounts_origin()
