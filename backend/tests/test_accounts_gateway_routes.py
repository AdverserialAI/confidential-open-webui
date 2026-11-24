"""Route-level tests for sign-in through the accounts service.

The real router and the real verification module are loaded; only the database-backed pieces of
Open WebUI are replaced by small in-memory stand-ins, so the tests need no database.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import sys
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parents[1] / 'open_webui'
ACCOUNTS = 'https://accounts.adverserial.ai'
CHAT = 'https://chat.adverserial.ai'
KEY = Ed25519PrivateKey.generate()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class IntegrityError(Exception):
    pass


class Store:
    """Stands in for the user table."""

    def __init__(self):
        self.users, self.sessions, self.revoked, self.ended, self.fail_insert = {}, [], [], [], False

    def add(self, uid, email, role='user', oauth=None):
        self.users[uid] = SimpleNamespace(id=uid, email=email, role=role, oauth=oauth or {}, name=email.split('@')[0])
        return self.users[uid]

    async def has_users(self, db=None):
        return bool(self.users)

    async def get_user_by_id(self, uid, db=None):
        return self.users.get(uid)

    async def get_user_by_email(self, email, db=None):
        return next((u for u in self.users.values() if u.email.lower() == email.lower()), None)

    async def get_user_by_oauth_sub(self, provider, sub, db=None):
        return next((u for u in self.users.values() if (u.oauth.get(provider) or {}).get('sub') == sub), None)

    async def update_user_oauth_by_id(self, uid, provider, sub, db=None):
        self.users[uid].oauth = {**self.users[uid].oauth, provider: {'sub': sub}}
        return self.users[uid]


STORE = Store()


async def signup_handler(request, email, password, name, profile_image_url='/user.png', *, db, source='api'):
    if STORE.fail_insert:
        raise IntegrityError()
    user = STORE.add(f'new{len(STORE.users) + 1}', email.lower())
    user.name, user.password, user.source = name, password, source
    return user


async def create_session_response(request, user, db, response=None, set_cookie=False, source='api'):
    if getattr(user, 'inactive', False):
        raise HTTPException(401, 'x')
    STORE.sessions.append((user.id, source))
    response.set_cookie('token', 'session-for-' + user.id, httponly=True, secure=True, samesite='lax')
    return {}


async def invalidate_token(request, token):
    STORE.ended.append(token)


async def revoke_user_tokens(request, uid):
    STORE.revoked.append(uid)


def _router():
    package = types.ModuleType('open_webui')
    package.__path__ = [str(BASE)]
    utils = types.ModuleType('open_webui.utils')
    utils.__path__ = [str(BASE / 'utils')]
    sys.modules.update({'open_webui': package, 'open_webui.utils': utils})
    gateway = _load('open_webui.utils.accounts_gateway', BASE / 'utils' / 'accounts_gateway.py')
    utils.accounts_gateway = gateway
    _load('open_webui.utils.identity', BASE / 'utils' / 'identity.py')
    stubs = {
        'open_webui.env': {'REDIS_KEY_PREFIX': 'test'},
        'open_webui.internal': {},
        'open_webui.internal.db': {'get_async_session': lambda: None},
        'open_webui.models': {},
        'open_webui.models.users': {'Users': STORE},
        'open_webui.routers': {},
        'open_webui.routers.auths': {'create_session_response': create_session_response, 'signup_handler': signup_handler},
        'open_webui.utils.auth': {'invalidate_token': invalidate_token, 'revoke_user_tokens': revoke_user_tokens},
        'sqlalchemy': {},
        'sqlalchemy.exc': {'IntegrityError': IntegrityError},
        'sqlalchemy.ext': {},
        'sqlalchemy.ext.asyncio': {'AsyncSession': object},
    }
    for name, attributes in stubs.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        sys.modules[name] = module
    return _load('accounts_gateway_router_under_test', BASE / 'routers' / 'accounts_gateway.py'), gateway


ROUTER, GATEWAY = _router()


class Redis:
    def __init__(self):
        self.seen = set()

    async def set(self, name, value, nx=False, ex=None):
        if name in self.seen:
            return None
        self.seen.add(name)
        return True


def signed(typ, **claims):
    now = int(time.time())
    body = {'iss': ACCOUNTS, 'aud': CHAT, 'typ': typ, 'jti': base64.urlsafe_b64encode(os.urandom(18)).decode(), 'iat': now, 'exp': now + 60}
    body.update(claims)
    return jwt.encode(body, KEY, algorithm='EdDSA', headers={'kid': 'k1'})


class Routes(unittest.TestCase):
    def setUp(self):
        raw = KEY.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.saved = dict(os.environ)
        os.environ['ACCOUNTS_GATEWAY_JWKS_JSON'] = json.dumps({'keys': [{
            'kty': 'OKP', 'crv': 'Ed25519', 'kid': 'k1', 'x': base64.urlsafe_b64encode(raw).decode().rstrip('=')}]})
        os.environ.pop('DYNO', None)
        STORE.__init__()
        STORE.add('u1', 'alice@example.test')
        app = FastAPI()
        app.state.redis = Redis()
        app.include_router(ROUTER.router, prefix='/api/v1/auths/accounts')
        self.client = TestClient(app, base_url=CHAT, follow_redirects=False)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)

    # ---- the browser handoff

    def exchange(self, token, origin=ACCOUNTS, cookies=None):
        return self.client.post('/api/v1/auths/accounts/exchange', data={'handoff': token}, headers={'Origin': origin} if origin else {},
                                cookies=cookies or {})

    def handoff(self, **claims):
        return signed(GATEWAY.HANDOFF_TYPE, **{'sub': 'alice@example.test', 'uid': 'u1', **claims})

    def test_a_handoff_becomes_this_chats_own_session_once(self):
        token = self.handoff()
        response = self.exchange(token)
        self.assertEqual((response.status_code, response.headers['location']), (303, '/'))
        cookie = response.headers['set-cookie']
        self.assertTrue(cookie.startswith('token=session-for-u1') and 'HttpOnly' in cookie and 'Secure' in cookie and 'Domain' not in cookie)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(STORE.sessions, [('u1', 'accounts')])
        again = self.exchange(token)
        self.assertEqual(again.status_code, 409)
        self.assertNotIn('set-cookie', again.headers)
        self.assertEqual(len(STORE.sessions), 1)

    def test_only_the_accounts_site_may_post_it(self):
        for origin in (CHAT, 'https://evil.example', None):
            response = self.exchange(self.handoff(), origin)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn('set-cookie', response.headers)
        self.assertEqual(STORE.sessions, [])

    def test_the_account_must_still_exist_match_and_be_allowed(self):
        STORE.add('u2', 'pending@example.test', role='pending')
        STORE.add('u3', 'gone@example.test').inactive = True
        cases = (self.handoff(uid='nobody'), self.handoff(sub='someone-else@example.test'),
                 self.handoff(uid='u2', sub='pending@example.test'), self.handoff(uid='u3', sub='gone@example.test'),
                 signed(GATEWAY.CALL_TYPE, sub='alice@example.test', uid='u1'), 'garbage', '')
        for token in cases:
            response = self.exchange(token)
            self.assertEqual(response.status_code, 401, token[:20])
            self.assertNotIn('set-cookie', response.headers)
            self.assertNotIn('alice', response.text)
        self.assertEqual(STORE.sessions, [])

    def test_a_refused_handoff_is_not_spent(self):
        # A handoff that fails its checks is not recorded as used, so a bad request cannot burn a good one's id.
        token = self.handoff(jti='a' * 24, uid='nobody')
        self.assertEqual(self.exchange(token).status_code, 401)
        self.assertEqual(self.exchange(self.handoff(jti='a' * 24)).status_code, 303)

    def test_the_previous_session_in_this_browser_is_ended(self):
        self.exchange(self.handoff(), cookies={'token': 'old-session'})
        self.assertEqual(STORE.ended, ['old-session'])

    def test_closed_when_not_configured(self):
        token = self.handoff()
        os.environ['ACCOUNTS_GATEWAY_JWKS_JSON'] = ''
        self.assertEqual(self.exchange(token).status_code, 503)

    # ---- calls from the accounts service

    def call(self, action, payload, sign_as=None, headers=None, body=None):
        raw = json.dumps(payload).encode() if body is None else body
        assertion = signed(GATEWAY.CALL_TYPE, act=sign_as or action, req=hashlib.sha256(json.dumps(payload).encode()).hexdigest())
        return self.client.post('/api/v1/auths/accounts/' + action, content=raw,
                                headers={'Content-Type': 'application/json', 'X-Accounts-Assertion': assertion, **(headers or {})})

    def test_provision_creates_a_password_account(self):
        response = self.call('provision', {'email': 'New@Example.test', 'name': '  New   Person ', 'password': 'a long phrase nobody guesses'})
        self.assertEqual(response.status_code, 200, response.text)
        user = STORE.users[response.json()['id']]
        self.assertEqual((user.email, user.name, user.password, user.source, user.oauth), ('new@example.test', 'New Person', 'a long phrase nobody guesses', 'accounts', {}))

    def test_provision_creates_a_google_account_with_a_password_nobody_knows(self):
        response = self.call('provision', {'email': 'g@example.test', 'name': '', 'google_sub': '1234567890'})
        self.assertEqual(response.status_code, 200, response.text)
        user = STORE.users[response.json()['id']]
        self.assertEqual((user.name, user.oauth), ('g', {'google': {'sub': '1234567890'}}))
        self.assertGreaterEqual(len(user.password), 48)

    def test_provision_refuses_what_it_should(self):
        good = 'a long phrase nobody guesses'
        STORE.add('u5', 'linked@example.test', oauth={'google': {'sub': 'taken'}})
        cases = {
            409: ({'email': 'alice@example.test', 'name': '', 'password': good}, {'email': 'ALICE@example.test', 'name': '', 'password': good},
                  {'email': 'x@example.test', 'name': '', 'google_sub': 'taken'}),
            400: ({'email': 'x@example.test', 'name': '', 'password': 'short'}, {'email': 'x@example.test', 'name': '', 'password': 'x' * 80},
                  {'email': 'x@example.test', 'name': ''}, {'email': 'x@example.test', 'name': '', 'password': good, 'google_sub': '1'},
                  {'email': ' x@example.test', 'name': '', 'password': good}, {'email': 'x@example.test', 'name': 'n' * 81, 'password': good},
                  {'email': 'x@example.test', 'name': '', 'google_sub': 'has space'}, {'email': 'x@example.test', 'name': '', 'password': 12345678901}),
        }
        before = len(STORE.users)
        for status, payloads in cases.items():
            for payload in payloads:
                self.assertEqual(self.call('provision', payload).status_code, status, payload)
        self.assertEqual(len(STORE.users), before)
        STORE.fail_insert = True
        self.assertEqual(self.call('provision', {'email': 'race@example.test', 'name': '', 'password': good}).status_code, 409)

    def test_provision_never_creates_the_first_account_which_would_be_the_administrator(self):
        STORE.users.clear()
        response = self.call('provision', {'email': 'first@example.test', 'name': '', 'password': 'a long phrase nobody guesses'})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(STORE.users, {})

    def test_an_oversized_handoff_is_refused(self):
        response = self.client.post('/api/v1/auths/accounts/exchange', content=b'handoff=' + b'a' * 20000,
                                    headers={'Origin': ACCOUNTS, 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code, 413)

    def test_calls_need_their_own_signature_and_work_once(self):
        payload = {'uid': 'u1'}
        self.assertEqual(self.call('revoke', payload).status_code, 200)
        self.assertEqual(STORE.revoked, ['u1'])
        self.assertEqual(self.call('revoke', payload, sign_as='link').status_code, 401)                 # signed for another action
        self.assertEqual(self.call('revoke', payload, body=b'{"uid": "u2"}').status_code, 401)           # body changed after signing
        self.assertEqual(self.call('revoke', payload, headers={'Origin': CHAT}).status_code, 403)        # a browser
        self.assertEqual(self.call('revoke', payload, headers={'Cookie': 'token=x'}).status_code, 403)
        self.assertEqual(self.client.post('/api/v1/auths/accounts/revoke', json=payload).status_code, 401)
        handoff = self.handoff()
        self.assertEqual(self.client.post('/api/v1/auths/accounts/revoke', content=json.dumps(payload),
                                          headers={'X-Accounts-Assertion': handoff}).status_code, 401)
        raw = json.dumps(payload).encode()
        assertion = signed(GATEWAY.CALL_TYPE, act='revoke', req=hashlib.sha256(raw).hexdigest())
        send = lambda: self.client.post('/api/v1/auths/accounts/revoke', content=raw, headers={'X-Accounts-Assertion': assertion})
        self.assertEqual((send().status_code, send().status_code), (200, 409))
        self.assertEqual(STORE.revoked, ['u1', 'u1'])

    def test_link_binds_one_google_identity_and_never_swaps_it(self):
        STORE.add('u2', 'bob@example.test')
        self.assertEqual(self.call('link', {'uid': 'u1', 'google_sub': 'g-alice'}).status_code, 200)
        self.assertEqual(STORE.users['u1'].oauth, {'google': {'sub': 'g-alice'}})
        self.assertEqual(self.call('link', {'uid': 'u1', 'google_sub': 'g-alice'}).status_code, 200)     # same again is harmless
        self.assertEqual(self.call('link', {'uid': 'u2', 'google_sub': 'g-alice'}).status_code, 409)     # someone else's identity
        self.assertEqual(self.call('link', {'uid': 'u1', 'google_sub': 'g-other'}).status_code, 409)     # no silent swap
        self.assertEqual(self.call('link', {'uid': 'nobody', 'google_sub': 'g-x'}).status_code, 404)
        self.assertEqual(self.call('link', {'uid': '../u1', 'google_sub': 'g-x'}).status_code, 400)
        self.assertEqual(STORE.users['u2'].oauth, {})


if __name__ == '__main__':
    unittest.main()
