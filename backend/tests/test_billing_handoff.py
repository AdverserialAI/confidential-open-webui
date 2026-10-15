"""Behavioral tests for the chat-to-billing handoff assertion.

This file deliberately loads the small router module with lightweight stubs so
the cryptographic contract can be verified without booting Open WebUI's full
database/application stack. The deployed environment imports the same source
with FastAPI and httpx installed.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import sys
import types
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROUTER_PATH = Path(__file__).resolve().parents[1] / 'open_webui' / 'routers' / 'confidential.py'


def _base64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _load_router_module():
    """Import the real router while stubbing framework-only dependencies."""

    class APIRouter:
        def get(self, *_args, **_kwargs):
            return lambda function: function

        def post(self, *_args, **_kwargs):
            return lambda function: function

    class HTTPException(Exception):
        pass

    fastapi = types.ModuleType('fastapi')
    fastapi.APIRouter = APIRouter
    fastapi.HTTPException = HTTPException
    fastapi.Request = object

    responses = types.ModuleType('fastapi.responses')
    responses.JSONResponse = object

    httpx = types.ModuleType('httpx')
    httpx.AsyncClient = object
    httpx.Timeout = object

    auth = types.ModuleType('open_webui.utils.auth')

    async def get_verified_user_by_token(*_args, **_kwargs):
        return None

    auth.get_verified_user_by_token = get_verified_user_by_token
    open_webui = types.ModuleType('open_webui')
    utils = types.ModuleType('open_webui.utils')

    injected = {
        'fastapi': fastapi,
        'fastapi.responses': responses,
        'httpx': httpx,
        'open_webui': open_webui,
        'open_webui.utils': utils,
        'open_webui.utils.auth': auth,
    }
    prior = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    try:
        spec = importlib.util.spec_from_file_location('confidential_router_under_test', ROUTER_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in prior.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class BillingHandoffTests(unittest.TestCase):
    def setUp(self):
        self.seed = bytes(range(32))
        self.previous_key = os.environ.get('BILLING_HANDOFF_PRIVATE_KEY')
        self.previous_kid = os.environ.get('BILLING_HANDOFF_KEY_ID')
        encoded_seed = base64.urlsafe_b64encode(self.seed).rstrip(b'=').decode('ascii')
        os.environ['BILLING_HANDOFF_PRIVATE_KEY'] = f'ed25519:{encoded_seed}'
        os.environ['BILLING_HANDOFF_KEY_ID'] = 'chat-2026-10'
        self.router = _load_router_module()

    def tearDown(self):
        for name, value in {
            'BILLING_HANDOFF_PRIVATE_KEY': self.previous_key,
            'BILLING_HANDOFF_KEY_ID': self.previous_kid,
        }.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_handoff_is_a_short_lived_signed_fixed_destination_assertion(self):
        issued_at = 1_700_000_000
        compact = self.router._mint_billing_handoff(
            email='  Operator@Example.COM ', destination='foothold', now=issued_at
        )
        encoded_header, encoded_claims, encoded_signature = compact.split('.')
        header = json.loads(_base64url_decode(encoded_header))
        claims = json.loads(_base64url_decode(encoded_claims))

        Ed25519PrivateKey.from_private_bytes(self.seed).public_key().verify(
            _base64url_decode(encoded_signature), f'{encoded_header}.{encoded_claims}'.encode('ascii')
        )
        self.assertEqual(header, {'alg': 'EdDSA', 'kid': 'chat-2026-10', 'typ': 'JWT'})
        self.assertEqual(claims['iss'], 'https://chat.adverserial.ai')
        self.assertEqual(claims['aud'], 'https://billing.adverserial.ai')
        self.assertEqual(claims['typ'], 'adverserial-billing-chat-handoff/v1')
        self.assertEqual(claims['sub'], 'operator@example.com')
        self.assertEqual(claims['destination'], 'foothold')
        self.assertEqual(claims['iat'], issued_at)
        self.assertEqual(claims['exp'], issued_at + 60)
        self.assertRegex(claims['jti'], r'^[0-9a-f-]{36}$')

    def test_handoff_rejects_unapproved_destinations_before_signing(self):
        with self.assertRaises(ValueError):
            self.router._mint_billing_handoff(
                email='operator@example.com', destination='https://attacker.invalid', now=1_700_000_000
            )

    def test_handoff_requires_an_actual_email_subject(self):
        for email in ('', '   ', 'none', 'user@', '@example.test', 'user@example.test extra'):
            with self.subTest(email=email), self.assertRaises(ValueError):
                self.router._mint_billing_handoff(email=email, destination='account', now=1_700_000_000)

    def test_handoff_rejects_malformed_signing_material(self):
        os.environ['BILLING_HANDOFF_PRIVATE_KEY'] = 'ed25519:not-base64!'
        with self.assertRaises(ValueError):
            self.router._mint_billing_handoff(email='operator@example.com', destination='account', now=1)


if __name__ == '__main__':
    unittest.main()
