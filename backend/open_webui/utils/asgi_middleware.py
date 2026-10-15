"""
Pure-ASGI replacements for the project's previous
`@app.middleware('http')` / `BaseHTTPMiddleware` middlewares.

Why this matters
----------------
Starlette's `BaseHTTPMiddleware` (which `@app.middleware('http')` is
sugar for) runs the downstream app inside an `anyio` task group. When
the wrapper exits — for any reason: response complete, client
disconnect, an outer middleware bailing out — the task group cancels
the inner task. That `CancelledError` then propagates into whatever
the inner task was doing, including in-flight DB queries, embedding
calls and disk I/O.

In Open WebUI this surfaces as:

* SQLAlchemy logging multi-page `NotImplementedError:
  terminate_force_close()` tracebacks at ERROR every time a request is
  cancelled mid-DB-call (the aiosqlite connector cleanup path).
* Spurious cancellations cascading through the four stacked
  `@app.middleware('http')` wrappers.

Pure ASGI middleware does not introduce a cancel scope around the
downstream app, so client disconnects propagate the way ASGI was
designed to (via `receive()` returning `http.disconnect`) instead of
being injected as `CancelledError` into arbitrary `await` points.

Reference: https://www.starlette.io/middleware/#limitations
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import parse_qs, urlencode

from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials
from open_webui.env import CUSTOM_API_KEY_HEADER
from open_webui.internal.db import ScopedSession
from open_webui.utils.auth import get_http_authorization_cred
from open_webui.utils.security_headers import set_security_headers
from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger(__name__)


class AppHTTPMiddleware:
    """Open WebUI's pure-ASGI HTTP middleware.

    Keeps the app's request-wide behavior in one middleware layer without
    hiding the old concerns behind a stack of wrappers:

    * reject malformed `/ws/socket.io` upgrade requests
    * stash bearer/cookie/API-key credentials on `request.state.token`
    * stamp `X-Process-Time` and configured security headers
    * serve the legacy `/watch` and `?shared=` redirects
    * commit and release the thread-local sync `ScopedSession`

    Most requests now use the async session; the sync ScopedSession is
    only touched by startup, healthchecks, and a handful of legacy
    helpers (notably the pgvector / opengauss vector-DB clients). The
    middleware exists so that PostgreSQL connections do not accumulate
    as "idle in transaction" and so that any pending sync work made
    inside the request is durably persisted.

    Failure semantics
    -----------------
    * Downstream raised → roll back any pending sync work, release the
      connection, and re-raise so the outer exception middleware can
      turn it into an error response. We never commit work on a
      request that did not complete successfully.
    * Downstream returned → commit pending sync work; on commit
      failure, log loudly, roll back, and re-raise. Note that in pure
      ASGI the response messages have already been emitted by the
      time `await self.app(...)` returns, so a commit failure cannot
      retroactively change what the client sees on the wire — but
      re-raising still surfaces the error in logs and to ASGI servers
      that expose it. We deliberately do not buffer the response to
      gate it on commit success, because that would defeat streaming
      responses (chat completions, SSE) which are core to the app.

    For request paths where commit-before-send is required, manage the
    sync session explicitly inside the handler instead of relying on
    this middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Headers derive only from env vars, which are static for the process
        # lifetime — compute them once instead of per response.
        self._security_headers = list(set_security_headers().items())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        if await self._reject_invalid_websocket(scope, receive, send):
            return

        start_time = time.monotonic()
        request = Request(scope)
        self._set_token(request)
        send_with_headers = self._send_with_headers(send, start_time)

        try:
            if await self._redirect_legacy_url(scope, receive, send_with_headers):
                pass
            # Keep health probes independent from sync session commit/remove so DB
            # pressure cannot delay or fail probe responses.
            elif scope.get('path', '') in {'/health', '/ready', '/health/db'}:
                await self.app(scope, receive, send_with_headers)
                return
            else:
                await self.app(scope, receive, send_with_headers)
        except BaseException:
            self._rollback_session('AppHTTPMiddleware: rollback failed after downstream error')
            raise

        self._commit_session()

    def _set_token(self, request: Request) -> None:
        token = get_http_authorization_cred(request.headers.get('Authorization'))
        if token is not None and token.credentials.lower() in {'undefined', 'null'}:
            token = None
        if token is None and (cookie_token := request.cookies.get('token')):
            token = HTTPAuthorizationCredentials(scheme='Bearer', credentials=cookie_token)
        if token is None and (api_key := request.headers.get(CUSTOM_API_KEY_HEADER)):
            token = HTTPAuthorizationCredentials(scheme='Bearer', credentials=api_key)
        request.state.token = token

    def _send_with_headers(self, send: Send, start_time: float) -> Send:
        async def send_with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers['X-Process-Time'] = f'{time.monotonic() - start_time:.6f}'
                for key, value in self._security_headers:
                    headers[key] = value
            await send(message)

        return send_with_headers

    async def _reject_invalid_websocket(self, scope: Scope, receive: Receive, send: Send) -> bool:
        path = scope.get('path', '')
        if '/ws/socket.io' not in path:
            return False

        query_params = parse_qs(scope.get('query_string', b'').decode('latin-1', errors='replace'))
        if query_params.get('transport', [''])[0] != 'websocket':
            return False

        headers = _scope_headers(scope)
        upgrade = headers.get('upgrade', '').lower()
        connection_tokens = [token.strip() for token in headers.get('connection', '').lower().split(',')]
        if upgrade == 'websocket' and 'upgrade' in connection_tokens:
            return False

        response = JSONResponse(status_code=400, content={'detail': 'Invalid WebSocket upgrade request'})
        await response(scope, receive, send)
        return True

    async def _redirect_legacy_url(self, scope: Scope, receive: Receive, send: Send) -> bool:
        if scope.get('method', '').upper() != 'GET':
            return False

        path = scope.get('path', '')
        raw_query = scope.get('query_string', b'')
        # This middleware only acts on /watch?v= and ?shared= URLs; skip the
        # decode + parse_qs work for every other GET. (A false positive on the
        # substring check just falls through to the full parse below.)
        if not (path.endswith('/watch') or b'shared' in raw_query):
            return False

        query_params = parse_qs(raw_query.decode('latin-1', errors='replace'))

        redirect_params: dict[str, str] = {}
        if path.endswith('/watch') and 'v' in query_params and query_params['v']:
            redirect_params['youtube'] = query_params['v'][0]

        if 'shared' in query_params and query_params['shared']:
            text = query_params['shared'][0]
            if text:
                url_match = re.match(r'https://\S+', text)
                if url_match:
                    # Local import: youtube loader pulls heavy deps and is
                    # only needed when a share-target actually contains a
                    # YouTube URL.
                    from open_webui.retrieval.loaders.youtube import _parse_video_id

                    youtube_video_id = _parse_video_id(url_match[0])
                    if youtube_video_id:
                        redirect_params['youtube'] = youtube_video_id
                    else:
                        redirect_params['load-url'] = url_match[0]
                else:
                    redirect_params['q'] = text

        if redirect_params:
            redirect_url = f'/?{urlencode(redirect_params)}'
            response = RedirectResponse(url=redirect_url)
            await response(scope, receive, send)
            return True

        return False

    def _rollback_session(self, message: str) -> None:
        if not ScopedSession.registry.has():
            return

        try:
            ScopedSession.rollback()
        except Exception:
            log.exception(message)
        finally:
            ScopedSession.remove()

    def _commit_session(self) -> None:
        # Nothing in this request touched the sync session: committing would
        # only instantiate one to run an empty transaction.
        if not ScopedSession.registry.has():
            return

        try:
            ScopedSession.commit()
        except Exception:
            log.exception('AppHTTPMiddleware: post-request commit failed; response was already sent to client')
            try:
                ScopedSession.rollback()
            except Exception:
                log.exception('AppHTTPMiddleware: rollback failed after commit failure')
            raise
        finally:
            # CRITICAL: remove() returns the connection to the pool.
            # Without this, connections remain "checked out" and
            # accumulate as "idle in transaction" in PostgreSQL.
            ScopedSession.remove()


def _scope_headers(scope: Scope) -> dict[str, str]:
    """Return ASGI scope headers as a lower-cased str→str dict.

    ASGI delivers headers as a list of (bytes, bytes) pairs. For
    convenience, fold duplicate keys with comma-joining (matching
    HTTP/1.1 semantics).
    """
    decoded: dict[str, str] = {}
    for raw_key, raw_value in scope.get('headers', []):
        key = raw_key.decode('latin-1').lower()
        value = raw_value.decode('latin-1')
        if key in decoded:
            decoded[key] = f'{decoded[key]}, {value}'
        else:
            decoded[key] = value
    return decoded


# adverserial: the chat UI lives on chat.adverserial.ai only;
# platform.adverserial.ai serves API/auth paths and redirects browsers.
CHAT_DOMAIN = os.getenv('CHAT_DOMAIN', 'chat.adverserial.ai')
PLATFORM_DOMAIN = os.getenv('PLATFORM_DOMAIN', 'platform.adverserial.ai')


class ChatDomainSplitMiddleware:
    """Redirect browser traffic on PLATFORM_DOMAIN to CHAT_DOMAIN.

    API/auth paths stay put so existing integrations using
    https://platform.adverserial.ai/api (docs, keys, OAuth) keep working;
    everything else — the SPA, /auth, static assets — gets a 308 to the
    chat host.
    """

    API_PREFIXES = ('/api', '/oauth', '/v1', '/ws', '/socket.io', '/health')

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or not CHAT_DOMAIN or not PLATFORM_DOMAIN:
            await self.app(scope, receive, send)
            return
        host = _scope_headers(scope).get('host', '').split(':')[0].strip().lower()
        if host != PLATFORM_DOMAIN:
            await self.app(scope, receive, send)
            return
        path = scope.get('path', '') or '/'
        if path.startswith(self.API_PREFIXES):
            await self.app(scope, receive, send)
            return
        query = scope.get('query_string', b'').decode('latin-1', errors='replace')
        target = f'https://{CHAT_DOMAIN}{path}' + (f'?{query}' if query else '')
        response = RedirectResponse(status_code=308, url=target)
        await response(scope, receive, send)

class ConfidentialOnlyMiddleware:
    """Fail closed before a request body reaches any legacy Open WebUI route.

    This distribution intentionally exposes no plaintext prompt, chat-history,
    file, retrieval, tool, or model-provider APIs.  Inference goes directly
    from the verified browser client to the attested runtime; this server only
    exposes the small account and entitlement contract under
    ``/api/v1/confidential``.  Keeping this at the ASGI boundary protects the
    guarantee even if an upstream router is added back accidentally in a
    future merge.
    """

    # The upstream app has a very large control plane. Prefix allow-lists made
    # every upstream route reachable again when it was mounted, including
    # provider configuration, API-key generation, and future routes added by a
    # merge. Keep the confidential runtime's browser contract intentionally
    # small and method-specific instead.
    _ALLOWED_API_METHODS = {
        '/api/config': frozenset({'GET', 'HEAD'}),
        '/api/version': frozenset({'GET', 'HEAD'}),
        '/api/models': frozenset({'GET', 'HEAD'}),
        '/api/v1/models': frozenset({'GET', 'HEAD'}),
        '/api/v1/auths/': frozenset({'GET', 'HEAD'}),
        '/api/v1/auths/signin': frozenset({'POST'}),
        '/api/v1/auths/signup': frozenset({'POST'}),
        '/api/v1/auths/ldap': frozenset({'POST'}),
        '/api/v1/auths/signout': frozenset({'POST'}),
        '/api/v1/auths/update/profile': frozenset({'POST'}),
        '/api/v1/auths/update/timezone': frozenset({'POST'}),
        '/api/v1/auths/update/password': frozenset({'POST'}),
        '/api/v1/users/user/settings': frozenset({'GET', 'HEAD'}),
        '/api/v1/users/user/settings/update': frozenset({'POST'}),
        '/api/v1/confidential/config': frozenset({'GET', 'HEAD'}),
        '/api/v1/confidential/account': frozenset({'GET', 'HEAD'}),
        '/api/v1/confidential/entitlements': frozenset({'POST'}),
        '/api/v1/confidential/billing-handoff': frozenset({'POST'}),
        '/health': frozenset({'GET', 'HEAD'}),
        '/ready': frozenset({'GET', 'HEAD'}),
        '/health/db': frozenset({'GET', 'HEAD'}),
    }
    _PROFILE_IMAGE_PATH = re.compile(r'^/api/v1/users/[A-Za-z0-9_-]{1,128}/profile/image$')
    # OAuth client registration lets the upstream app act as a generic OAuth
    # client for arbitrary tool servers.  The confidential distribution only
    # needs a configured identity-provider login and callback.  Likewise the
    # cache endpoint can disclose persisted tool/file output from a restored
    # upstream installation.  Do not let the SPA fallback make either surface
    # reachable again.
    _OAUTH_LOGIN_PATH = re.compile(
        r'^/oauth/[A-Za-z0-9_-]{1,64}/(?:login|login/callback|callback)$'
    )
    _BLOCKED_PUBLIC_PREFIXES = ('/oauth/clients/', '/cache/')
    _BLOCKED_PUBLIC_PATHS = frozenset({'/oauth/backchannel-logout', '/opensearch.xml'})
    _READ_ONLY_METHODS = frozenset({'GET', 'HEAD'})
    _UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _allows(self, path: str, method: str) -> bool:
        # The Svelte app needs read-only routing for assets and client-side
        # pages.  That does *not* imply every upstream non-API endpoint is
        # safe: reject server-side OAuth-client and cache routes explicitly.
        # Only configured identity-provider login callbacks are needed.
        if path != '/api' and not path.startswith('/api/'):
            if path in self._BLOCKED_PUBLIC_PATHS or path.startswith(self._BLOCKED_PUBLIC_PREFIXES):
                return False
            if path.startswith('/oauth/'):
                return method in self._READ_ONLY_METHODS and bool(self._OAUTH_LOGIN_PATH.fullmatch(path))
            return method in self._READ_ONLY_METHODS
        methods = self._ALLOWED_API_METHODS.get(path)
        if methods is None and self._PROFILE_IMAGE_PATH.fullmatch(path):
            methods = frozenset({'GET', 'HEAD'})
        if methods is None:
            return False
        # CORS preflight must reach the CORS layer, but only for a route that
        # this middleware otherwise exposes.
        return method == 'OPTIONS' or method in methods

    @staticmethod
    def _has_session_cookie(headers: dict[str, str]) -> bool:
        for part in headers.get('cookie', '').split(';'):
            name, _separator, value = part.strip().partition('=')
            if name == 'token' and value:
                return True
        return False

    @staticmethod
    def _has_bearer_credential(headers: dict[str, str]) -> bool:
        authorization = headers.get('authorization', '').strip()
        if not authorization.lower().startswith('bearer '):
            return False
        value = authorization[7:].strip().lower()
        return bool(value and value not in {'undefined', 'null'})

    @staticmethod
    def _is_chat_origin(origin: str) -> bool:
        # CHAT_DOMAIN is an operator-controlled hostname, not request input.
        # The production route is HTTPS; permit HTTP only for explicit local
        # development hosts.
        domain = CHAT_DOMAIN.strip().lower().rstrip('/')
        allowed = {f'https://{domain}'}
        if domain.startswith('localhost') or domain.startswith('127.0.0.1') or domain.startswith('[::1]'):
            allowed.add(f'http://{domain}')
        return origin.strip().lower().rstrip('/') in allowed

    def _allows_cookie_mutation(self, scope: Scope) -> bool:
        """Require a same-origin browser for state changes made with a cookie.

        Bearer/API clients remain compatible. A cross-site form or fetch cannot
        forge the browser Origin header, so it cannot spend a signed-in user's
        billing handoff or mutate account state merely by carrying their cookie.
        For unauthenticated sign-in and sign-up requests, browsers do not carry
        a session cookie yet; reject an explicit cross-site Fetch Metadata
        signal as well, preventing login-CSRF without blocking headerless CLI
        clients.
        """

        if scope.get('method', '').upper() not in self._UNSAFE_METHODS:
            return True
        headers = _scope_headers(scope)
        if self._has_bearer_credential(headers):
            return True
        origin = headers.get('origin', '')
        if origin:
            return self._is_chat_origin(origin)
        if self._has_session_cookie(headers):
            return False
        # A browser cross-site navigation/form submits this header even before
        # it has a session cookie. A headerless non-browser client remains
        # compatible with the documented API sign-in flow.
        return headers.get('sec-fetch-site', '').strip().lower() != 'cross-site'

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            # This runtime does not expose Open WebUI's Socket.IO / websocket
            # surface.  Explicitly close rather than leaving a client hanging
            # if an upstream router or mount is restored later.
            if scope['type'] == 'websocket':
                await send({'type': 'websocket.close', 'code': 1008})
            return
        path = scope.get('path', '') or '/'
        method = scope.get('method', 'GET').upper()
        if self._allows(path, method) and self._allows_cookie_mutation(scope):
            await self.app(scope, receive, send)
            return
        if self._allows(path, method):
            response = JSONResponse(status_code=403, content={'detail': 'Same-origin browser request required.'})
            await response(scope, receive, send)
            return
        response = JSONResponse(
            status_code=404,
            content={
                'detail': 'This confidential-only distribution does not expose plaintext prompt or server transcript routes.'
            },
        )
        await response(scope, receive, send)
