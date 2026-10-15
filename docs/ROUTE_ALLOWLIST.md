# Route allow-list

The public upstream history intentionally remains available for license and audit context. It is not the deployed confidential runtime surface.

`ConfidentialOnlyMiddleware` is outermost in `backend/open_webui/main.py`. It rejects every API path unless its exact path *and HTTP method* are part of the confidential browser contract:

- sign-in/out, password/profile/timezone changes, and the signed-in session lookup;
- the current user's UI settings and profile image;
- configuration and confidential-model discovery;
- confidential runtime configuration, count-only account display, entitlement issuance, and the one-time billing handoff; and
- health checks.

Cookie-authenticated state changes must also carry a same-origin `Origin` header. Bearer/API clients remain supported where the route itself is exposed. The distribution does not mount upstream configuration or model-management routers, and the middleware independently rejects them if a future merge reintroduces one.

Unauthenticated sign-in and sign-up requests have no session cookie to check, so the middleware also rejects browser requests marked `Sec-Fetch-Site: cross-site`. Headerless non-browser API clients remain compatible with their documented login flow.

Production CORS defaults to `https://chat.adverserial.ai`; it must never be `*` while cookie authentication is enabled. An inherited production wildcard is discarded in favor of the chat origin while explicitly configured origins are retained. This prevents another site from reading a signed-in browser's account or session responses.

Non-API traffic is read-only only. Static assets and client-side Svelte routes remain available, as do configured identity-provider login and callback paths (`/oauth/<provider>/login` and its callbacks). The upstream OAuth-client registration/callback surface, cache-file serving, backchannel logout, OpenSearch, and every WebSocket connection are rejected. This avoids accidentally restoring a tool-server, persisted-file, or realtime control-plane path through the SPA fallback.

## Billing handoff

The browser never posts an Open WebUI session JWT to the billing origin. `/billing` requests a same-origin, short-lived handoff from `/api/v1/confidential/billing-handoff`, then performs a top-level form POST containing only the signed `handoff` value to `https://billing.adverserial.ai/account/session/exchange`.

Configure chat with a dedicated, sealed Ed25519 signing seed and key identifier:

```text
BILLING_HANDOFF_PRIVATE_KEY=ed25519:<base64url-encoded-32-byte-seed>
BILLING_HANDOFF_KEY_ID=<stable-key-id>
```

Billing receives only the matching public JWK in `BILLING_CHAT_HANDOFF_JWKS_JSON`. Each assertion has a fixed issuer, audience, type, signed destination, normalized email subject, random `jti`, and a 60-second maximum lifetime. Billing atomically consumes the `jti`, so replayed assertions fail.

It blocks standard `/openai`, `/ollama`, `/api/chat/completions`, `/api/v1/chat/completions`, chat records, uploads, retrieval, tools, functions, prompts, skills, memories, tasks, automations, calendars and WebSockets before a body is consumed. The upstream UI source remains in the repository for provenance and styling, but its server routes are neither mounted nor allow-listed in this distribution.

The direct confidential SSE parser accepts only OpenAI-compatible choice deltas,
usage metadata, and the final signed receipt. It does not dispatch generic
Open WebUI tool events. The retained UI’s legacy remote `execute` event is
explicitly disabled, so an event object can never become browser JavaScript.
