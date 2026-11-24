"""Behavioral tests for sign-in through the accounts service.

The verification module imports only the standard library and PyJWT, so the real source is loaded
directly and exercised with real Ed25519 signatures: no database, no application stack.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PATH = Path(__file__).resolve().parents[1] / 'open_webui' / 'utils' / 'accounts_gateway.py'
spec = importlib.util.spec_from_file_location('accounts_gateway_under_test', PATH)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

ACCOUNTS = 'https://accounts.adverserial.ai'
CHAT = 'https://chat.adverserial.ai'
KEY = Ed25519PrivateKey.generate()
OTHER = Ed25519PrivateKey.generate()


def jwks(key, kid='k1'):
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return json.dumps({'keys': [{'kty': 'OKP', 'crv': 'Ed25519', 'kid': kid, 'x': base64.urlsafe_b64encode(raw).decode().rstrip('=')}]})


def token(key=KEY, kid='k1', alg='EdDSA', **changes):
    now = int(time.time())
    claims = {'iss': ACCOUNTS, 'aud': CHAT, 'typ': gateway.HANDOFF_TYPE, 'sub': 'alice@example.test', 'uid': 'u1',
              'jti': 'j' * 24, 'iat': now, 'exp': now + 60}
    claims.update(changes)
    claims = {name: value for name, value in claims.items() if value is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={'kid': kid})


def call(body, action='signin', **changes):
    return token(typ=gateway.CALL_TYPE, sub=None, uid=None, act=action, req=hashlib.sha256(body).hexdigest(), **changes)


class Redis:
    def __init__(self, fail=False):
        self.seen, self.fail = {}, fail

    async def set(self, name, value, nx=False, ex=None):
        if self.fail:
            raise RuntimeError('down')
        if nx and name in self.seen:
            return None
        self.seen[name] = ex
        return True


class Request:
    def __init__(self, body=b'', headers=None, redis=None):
        self._body, self.headers = body, {'content-length': str(len(body)), **{k.lower(): v for k, v in (headers or {}).items()}}
        self.app = SimpleNamespace(state=SimpleNamespace(redis=redis))

    async def body(self):
        return self._body


def refused(test, status, function, *args):
    with test.assertRaises(gateway.Refused) as caught:
        result = function(*args)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    test.assertEqual(caught.exception.status, status)


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = dict(os.environ)
        for name in ('ACCOUNTS_GATEWAY', 'ACCOUNTS_GATEWAY_ORIGIN', 'CHAT_DOMAIN', 'DYNO', 'ACCOUNTS_GATEWAY_REQUIRE_SHARED_STORE'):
            os.environ.pop(name, None)
        os.environ['ACCOUNTS_GATEWAY_JWKS_JSON'] = jwks(KEY)
        gateway._memory_seen.clear()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)


class Configuration(Base):
    def test_off_until_a_key_is_configured_and_the_switch_is_on(self):
        self.assertTrue(gateway.configured())
        self.assertFalse(gateway.enforced())
        os.environ['ACCOUNTS_GATEWAY'] = '1'
        self.assertTrue(gateway.enforced())
        os.environ['ACCOUNTS_GATEWAY_JWKS_JSON'] = ''
        self.assertFalse(gateway.configured())
        # A broken key never reopens the old way in: the switch stays on and every check refuses.
        self.assertTrue(gateway.enforced())
        self.assertTrue(gateway.misconfigured())
        refused(self, 503, gateway.verify_call, 'x', 'signin', b'')
        for value in ('true', 'TRUE', 'on', ' 1 '):
            os.environ['ACCOUNTS_GATEWAY'] = value
            self.assertTrue(gateway.enforced(), value)
        for value in ('', '0', 'false', 'off'):
            os.environ['ACCOUNTS_GATEWAY'] = value
            self.assertFalse(gateway.enforced(), value)
            self.assertFalse(gateway.misconfigured(), value)

    def test_bad_key_material_configures_nothing(self):
        private = json.loads(jwks(KEY))
        private['keys'][0]['d'] = 'AAAA'
        for value in ('not json', '[]', '{"keys":"x"}', '{"keys":[{"kty":"RSA","kid":"k1"}]}', json.dumps(private)):
            os.environ['ACCOUNTS_GATEWAY_JWKS_JSON'] = value
            self.assertEqual(gateway.keys(), {}, value)

    def test_only_an_https_accounts_origin_is_accepted(self):
        for value in ('http://accounts.adverserial.ai', 'https://accounts.adverserial.ai/path', 'javascript:alert(1)', 'https://a b', ''):
            os.environ['ACCOUNTS_GATEWAY_ORIGIN'] = value
            if value:
                self.assertEqual(gateway.accounts_origin(), '', value)
                self.assertFalse(gateway.configured(), value)


class Handoff(Base):
    def test_a_good_handoff_names_the_account(self):
        self.assertEqual(gateway.verify_handoff(token())['uid'], 'u1')
        self.assertEqual(gateway.verify_handoff(token())['email'], 'alice@example.test')

    def test_wrong_signer_audience_issuer_type_or_time_is_refused(self):
        now = int(time.time())
        cases = {
            'another key': token(key=OTHER),
            'unknown key id': token(kid='k2'),
            'another audience': token(aud='https://billing.adverserial.ai'),
            'another issuer': token(iss='https://evil.example'),
            'a billing handoff': token(typ='adverserial-billing-accounts-handoff/v1'),
            'a call used as a handoff': token(typ=gateway.CALL_TYPE),
            'expired': token(iat=now - 120, exp=now - 60),
            'lives too long': token(exp=now + 3600),
            'from the future': token(iat=now + 600, exp=now + 630),
            'no id': token(jti=None),
            'short id': token(jti='abc'),
            'no account': token(uid=None),
            'odd account': token(uid='../x'),
            'no address': token(sub=None),
            'text times': token(iat=str(now), exp=str(now + 30)),
        }
        for name, value in cases.items():
            with self.subTest(name):
                refused(self, 401, gateway.verify_handoff, value)

    def test_unsigned_and_wrong_algorithm_tokens_are_refused(self):
        now = int(time.time())
        claims = {'iss': ACCOUNTS, 'aud': CHAT, 'typ': gateway.HANDOFF_TYPE, 'sub': 'alice@example.test', 'uid': 'u1',
                  'jti': 'j' * 24, 'iat': now, 'exp': now + 60}
        part = lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
        unsigned = part({'alg': 'none', 'kid': 'k1'}) + '.' + part(claims) + '.'
        hmac = jwt.encode(claims, 'x' * 32, algorithm='HS256', headers={'kid': 'k1'})
        for value in (unsigned, hmac, '', 'a.b.c', None, 5, 'x' * 5000):
            refused(self, 401, gateway.verify_handoff, value)

    def test_nothing_is_accepted_when_not_configured(self):
        good = token()
        os.environ['ACCOUNTS_GATEWAY_JWKS_JSON'] = ''
        refused(self, 503, gateway.verify_handoff, good)


class Calls(Base):
    def test_a_call_is_bound_to_its_action_and_body(self):
        body = b'{"email":"alice@example.test","password":"correct horse"}'
        self.assertIn('jti', gateway.verify_call(call(body), 'signin', body))
        refused(self, 401, gateway.verify_call, call(body), 'signin', body + b' ')
        refused(self, 401, gateway.verify_call, call(body), 'provision', body)
        refused(self, 401, gateway.verify_call, call(body, key=OTHER), 'signin', body)
        refused(self, 401, gateway.verify_call, token(), 'signin', body)          # a handoff is not a call
        refused(self, 404, gateway.verify_call, call(body, action='delete'), 'delete', body)

    def test_a_browser_can_never_make_a_call(self):
        body = b'{}'
        for header in ({'Origin': CHAT}, {'Cookie': 'token=x'}, {'Sec-Fetch-Site': 'same-origin'}):
            request = Request(body, {'X-Accounts-Assertion': call(body), **header}, Redis())
            refused(self, 403, gateway.server_call, request, 'signin', 'p')

    def test_a_call_works_once(self):
        body, redis = b'{"uid":"u1"}', Redis()
        signed = call(body, action='revoke')
        request = lambda: Request(body, {'X-Accounts-Assertion': signed}, redis)
        self.assertEqual(asyncio.run(gateway.server_call(request(), 'revoke', 'p')), body)
        refused(self, 409, gateway.server_call, request(), 'revoke', 'p')

    def test_a_call_without_a_signature_or_with_a_large_body_is_refused(self):
        refused(self, 401, gateway.server_call, Request(b'{}', {}, Redis()), 'signin', 'p')
        big = b'x' * (gateway.MAX_BODY + 1)
        refused(self, 413, gateway.server_call, Request(big, {'X-Accounts-Assertion': call(big)}, Redis()), 'signin', 'p')

    def test_the_size_is_checked_before_anything_is_read(self):
        class Unread(Request):
            async def body(self):
                raise AssertionError('the body was read')
        refused(self, 413, gateway.server_call, Unread(b'', {'Content-Length': str(gateway.MAX_BODY + 1)}, Redis()), 'signin', 'p')
        refused(self, 411, gateway.server_call, Unread(b'', {'Content-Length': ''}, Redis()), 'signin', 'p')
        refused(self, 411, gateway.server_call, Unread(b'', {'Content-Length': '-5'}, Redis()), 'signin', 'p')


class Replay(Base):
    def test_shared_store_accepts_once(self):
        redis = Redis()
        asyncio.run(gateway.consume(redis, 'p', 'j' * 24, int(time.time()) + 60))
        refused(self, 409, gateway.consume, redis, 'p', 'j' * 24, int(time.time()) + 60)
        self.assertNotIn('j' * 24, ''.join(redis.seen))       # the id itself is not kept, only its hash

    def test_a_failing_store_refuses(self):
        refused(self, 503, gateway.consume, Redis(fail=True), 'p', 'j' * 24, int(time.time()) + 60)

    def test_one_process_remembers_but_a_hosted_one_needs_the_shared_store(self):
        asyncio.run(gateway.consume(None, 'p', 'k' * 24, int(time.time()) + 60))
        refused(self, 409, gateway.consume, None, 'p', 'k' * 24, int(time.time()) + 60)
        os.environ['DYNO'] = 'web.1'
        refused(self, 503, gateway.consume, None, 'p', 'm' * 24, int(time.time()) + 60)


class HandoffOrigin(Base):
    def test_only_the_accounts_site_may_post_a_handoff(self):
        self.assertTrue(gateway.browser_handoff_origin_ok(Request(headers={'Origin': ACCOUNTS})))
        for origin in ('', CHAT, 'https://accounts.adverserial.ai.evil.example', 'http://accounts.adverserial.ai', 'null'):
            self.assertFalse(gateway.browser_handoff_origin_ok(Request(headers={'Origin': origin})), origin)


if __name__ == '__main__':
    unittest.main()
