"""Behavioral tests for the confidential-only ASGI surface.

The real module normally imports the full Open WebUI runtime.  These focused
tests load the same source with tiny framework stubs so the request gate can be
verified without starting a database or model service.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


MIDDLEWARE_PATH = Path(__file__).resolve().parents[1] / 'open_webui' / 'utils' / 'asgi_middleware.py'


def _load_middleware_module():
    class JSONResponse:
        def __init__(self, *args, **kwargs):
            pass

        async def __call__(self, *_args, **_kwargs):
            return None

    class RedirectResponse(JSONResponse):
        pass

    class HTTPAuthorizationCredentials:
        def __init__(self, scheme: str, credentials: str):
            self.scheme = scheme
            self.credentials = credentials

    class ScopedSession:
        class registry:
            @staticmethod
            def has():
                return False

    class MutableHeaders:
        def __init__(self, *args, **kwargs):
            pass

    fastapi = types.ModuleType('fastapi')
    responses = types.ModuleType('fastapi.responses')
    responses.JSONResponse = JSONResponse
    responses.RedirectResponse = RedirectResponse
    security = types.ModuleType('fastapi.security')
    security.HTTPAuthorizationCredentials = HTTPAuthorizationCredentials

    env = types.ModuleType('open_webui.env')
    env.CUSTOM_API_KEY_HEADER = 'x-api-key'
    db = types.ModuleType('open_webui.internal.db')
    db.ScopedSession = ScopedSession
    auth = types.ModuleType('open_webui.utils.auth')
    auth.get_http_authorization_cred = lambda _value: None
    security_headers = types.ModuleType('open_webui.utils.security_headers')
    security_headers.set_security_headers = lambda: {}

    datastructures = types.ModuleType('starlette.datastructures')
    datastructures.MutableHeaders = MutableHeaders
    requests = types.ModuleType('starlette.requests')
    requests.Request = object
    starlette_types = types.ModuleType('starlette.types')
    starlette_types.ASGIApp = object
    starlette_types.Message = dict
    starlette_types.Receive = object
    starlette_types.Scope = dict
    starlette_types.Send = object

    open_webui = types.ModuleType('open_webui')
    internal = types.ModuleType('open_webui.internal')
    utils = types.ModuleType('open_webui.utils')
    starlette = types.ModuleType('starlette')
    injected = {
        'fastapi': fastapi,
        'fastapi.responses': responses,
        'fastapi.security': security,
        'open_webui': open_webui,
        'open_webui.env': env,
        'open_webui.internal': internal,
        'open_webui.internal.db': db,
        'open_webui.utils': utils,
        'open_webui.utils.auth': auth,
        'open_webui.utils.security_headers': security_headers,
        'starlette': starlette,
        'starlette.datastructures': datastructures,
        'starlette.requests': requests,
        'starlette.types': starlette_types,
    }
    prior = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)
    try:
        spec = importlib.util.spec_from_file_location('asgi_middleware_under_test', MIDDLEWARE_PATH)
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


class ConfidentialOnlyMiddlewareTests(unittest.TestCase):
    def setUp(self):
        module = _load_middleware_module()
        self.middleware = module.ConfidentialOnlyMiddleware(lambda _scope, _receive, _send: None)

    def test_allows_only_read_only_spa_and_identity_provider_paths(self):
        checks = {
            ('/', 'GET'): True,
            ('/auth', 'HEAD'): True,
            ('/', 'POST'): False,
            ('/oauth/google/login', 'GET'): True,
            ('/oauth/google/login/callback', 'GET'): True,
            ('/oauth/google/callback', 'GET'): True,
            ('/oauth/google/login', 'POST'): False,
            ('/oauth/clients/tool/authorize', 'GET'): False,
            ('/oauth/backchannel-logout', 'POST'): False,
            ('/cache/persisted-tool-output', 'GET'): False,
            ('/opensearch.xml', 'GET'): False,
        }
        for request, expected in checks.items():
            with self.subTest(request=request):
                self.assertIs(self.middleware._allows(*request), expected)

    def test_api_paths_are_exact_and_method_specific(self):
        self.assertTrue(self.middleware._allows('/api/v1/confidential/billing-handoff', 'POST'))
        self.assertFalse(self.middleware._allows('/api/v1/confidential/billing-handoff', 'GET'))
        self.assertFalse(self.middleware._allows('/api/v1/configs', 'GET'))
        self.assertFalse(self.middleware._allows('/api/v1/chats', 'GET'))

    def test_cookie_mutations_and_login_csrf_require_a_trusted_browser_context(self):
        cookie_scope = {
            'method': 'POST',
            'headers': [(b'cookie', b'token=session-token')],
        }
        cross_site_login_scope = {
            'method': 'POST',
            'headers': [(b'sec-fetch-site', b'cross-site')],
        }
        same_origin_scope = {
            'method': 'POST',
            'headers': [(b'origin', b'https://chat.adverserial.ai')],
        }
        bearer_scope = {
            'method': 'POST',
            'headers': [(b'authorization', b'Bearer api-client-token')],
        }
        self.assertFalse(self.middleware._allows_cookie_mutation(cookie_scope))
        self.assertFalse(self.middleware._allows_cookie_mutation(cross_site_login_scope))
        self.assertTrue(self.middleware._allows_cookie_mutation(same_origin_scope))
        self.assertTrue(self.middleware._allows_cookie_mutation(bearer_scope))

    def test_websocket_connections_are_explicitly_closed(self):
        sent = []

        async def receive():
            return {'type': 'websocket.connect'}

        async def send(message):
            sent.append(message)

        asyncio.run(self.middleware({'type': 'websocket', 'path': '/ws/socket.io'}, receive, send))
        self.assertEqual(sent, [{'type': 'websocket.close', 'code': 1008}])


if __name__ == '__main__':
    unittest.main()
