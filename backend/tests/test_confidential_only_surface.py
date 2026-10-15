from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'open_webui' / 'main.py').read_text()
MIDDLEWARE = (ROOT / 'open_webui' / 'utils' / 'asgi_middleware.py').read_text()
CONFIDENTIAL_ROUTER = (ROOT / 'open_webui' / 'routers' / 'confidential.py').read_text()
CLIENT = (ROOT.parent / 'src' / 'lib' / 'confidential' / 'client.ts').read_text()
CHAT = (ROOT.parent / 'src' / 'lib' / 'components' / 'chat' / 'Chat.svelte').read_text()
MEMBERSHIP_USAGE = (ROOT.parent / 'src' / 'lib' / 'components' / 'layout' / 'Sidebar' / 'MembershipUsage.svelte').read_text()


def test_only_confidential_inference_router_is_mounted():
    forbidden = (
        "app.include_router(openai.router",
        "app.include_router(ollama.router",
        "app.include_router(chats.router",
        "app.include_router(files.router",
        "app.include_router(retrieval.router",
        "app.include_router(tools.router",
        "app.include_router(pipelines.router",
        "app.include_router(configs.router",
        "app.include_router(models.router",
    )
    assert all(item not in MAIN for item in forbidden)
    assert "app.include_router(confidential.router" in MAIN


def test_control_plane_prefixes_cannot_be_reintroduced_through_the_allow_list():
    # These are high-impact upstream routers: provider credentials, API keys,
    # model management, and future subroutes must remain unreachable even if a
    # source merge restores their router imports.
    for prefix in ("'/api/v1/configs'", "'/api/v1/models/'", "'/api/v1/users/'", "'/api/v1/auths'"):
        assert prefix not in MIDDLEWARE
    assert "_ALLOWED_API_METHODS" in MIDDLEWARE
    assert "_allows_cookie_mutation" in MIDDLEWARE
    assert "Same-origin browser request required" in MIDDLEWARE


def test_production_cors_defaults_to_the_chat_origin():
    config = (ROOT / 'open_webui' / 'config.py').read_text()
    assert "https://{os.getenv('CHAT_DOMAIN', 'chat.adverserial.ai')" in config
    assert "if _cors_env in {'prod', 'production'}" in config
    assert "origin for origin in _cors_configured if origin != '*'" in config


def test_plaintext_routes_are_rejected_before_body_processing():
    assert "class ConfidentialOnlyMiddleware" in MIDDLEWARE
    assert "'/api/v1/confidential/entitlements'" in MIDDLEWARE
    assert "does not expose plaintext prompt or server transcript routes" in MIDDLEWARE


def test_non_api_upstream_control_planes_cannot_hide_behind_the_spa_fallback():
    # The Svelte SPA needs GET/HEAD fallback, but its fallback must never make
    # restored upstream OAuth-client registration, cache files, backchannel
    # logout, or WebSockets available.
    for blocked in ("'/oauth/clients/'", "'/cache/'", "'/oauth/backchannel-logout'", "'/opensearch.xml'"):
        assert blocked in MIDDLEWARE
    assert '_OAUTH_LOGIN_PATH' in MIDDLEWARE
    assert "'websocket.close'" in MIDDLEWARE


def test_open_webui_does_not_accept_a_ciphertext_relay():
    assert '@router.post("/relay/chat/completions")' not in CONFIDENTIAL_ROUTER
    assert 'relay_ciphertext' not in CONFIDENTIAL_ROUTER
    assert 'CONFIDENTIAL_MAX_CIPHERTEXT_BYTES' not in CONFIDENTIAL_ROUTER


def test_browser_confidential_transport_stays_direct_to_the_attested_api():
    assert 'relayFetch' not in CLIENT
    assert '/api/v1/confidential/relay' not in CLIENT
    assert 'fetchImpl: fetch' in CLIENT


def test_legacy_event_execution_cannot_evaluate_remote_code():
    assert 'new Function' not in CHAT
    assert 'Ignoring disabled remote execute event.' in CHAT


def test_membership_usage_does_not_send_a_browser_token_to_billing():
    assert 'https://billing.adverserial.ai' not in MEMBERSHIP_USAGE
    assert '/api/v1/confidential/account' in MEMBERSHIP_USAGE
    assert "credentials: 'include'" in MEMBERSHIP_USAGE
