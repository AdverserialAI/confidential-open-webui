"""HTTPS only, and no caching of account answers.

The middleware class is loaded on its own, as the confidential-surface tests do, so no database or
model service is needed.
"""

import os
import unittest
from pathlib import Path

from starlette.applications import Starlette
from starlette.datastructures import MutableHeaders  # noqa: F401  (used by the loaded class)
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send  # noqa: F401

SOURCE = (Path(__file__).resolve().parents[1] / 'open_webui' / 'utils' / 'asgi_middleware.py').read_text()
exec(SOURCE[SOURCE.index('class TransportMiddleware'):])


class Transport(unittest.TestCase):
    def test_plain_http_is_never_served_and_api_answers_are_not_cached(self):
        os.environ.pop('DYNO', None)
        async def me(request): return JSONResponse({'token': 'secret'})
        async def models(request): return JSONResponse({'ok': 1}, headers={'Cache-Control': 'max-age=60'})
        async def page(request): return PlainTextResponse('page')
        async def signin(request): return JSONResponse({'token': 't'})
        def build():
            app = Starlette(routes=[Route('/api/v1/auths/', me), Route('/api/models', models), Route('/', page), Route('/api/v1/auths/signin', signin, methods=['POST'])])
            return TestClient(TransportMiddleware(app), base_url='https://chat.adverserial.ai')
        c = build()                                               # not on the platform: plain HTTP is left alone (local development)
        assert c.get('/', headers={'X-Forwarded-Proto': 'http'}).status_code == 200
        assert c.get('/api/v1/auths/').headers['cache-control'] == 'no-store'
        assert c.get('/api/models').headers['cache-control'] == 'max-age=60'          # an answer that says how to cache keeps its own rule
        assert 'cache-control' not in c.get('/').headers                               # pages and assets are untouched
        os.environ['DYNO'] = 'web.1'
        self.addCleanup(os.environ.pop, 'DYNO', None)
        c = build()
        plain = {'X-Forwarded-Proto': 'http'}
        r = c.get('/auth?redirect=%2Fbilling', headers=plain, follow_redirects=False)
        assert (r.status_code, r.headers['location']) == (308, 'https://chat.adverserial.ai/auth?redirect=%2Fbilling'), (r.status_code, r.headers)
        r = c.get('/x', headers={**plain, 'Host': 'platform.adverserial.ai'}, follow_redirects=False)
        assert r.headers['location'] == 'https://platform.adverserial.ai/x'
        r = c.get('/x', headers={**plain, 'Host': 'evil.example'}, follow_redirects=False)
        assert r.headers['location'] == 'https://chat.adverserial.ai/x'                # never a name taken from the request
        r = c.post('/api/v1/auths/signin', json={'email': 'a', 'password': 'b'}, headers=plain)
        assert (r.status_code, r.json()) == (400, {'detail': 'HTTPS required'})         # credentials are not accepted in clear text
        assert c.post('/api/v1/auths/signin', json={}, headers={'X-Forwarded-Proto': 'https'}).status_code == 200
        assert c.post('/api/v1/auths/signin', json={}, headers={'X-Forwarded-Proto': 'http, https'}).status_code == 200   # the router's own entry is last
        assert c.get('/', headers={'X-Forwarded-Proto': 'https'}).status_code == 200


if __name__ == '__main__':
    unittest.main()
