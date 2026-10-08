from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'open_webui' / 'main.py').read_text()
MIDDLEWARE = (ROOT / 'open_webui' / 'utils' / 'asgi_middleware.py').read_text()
CONFIDENTIAL_ROUTER = (ROOT / 'open_webui' / 'routers' / 'confidential.py').read_text()
CLIENT = (ROOT.parent / 'src' / 'lib' / 'confidential' / 'client.ts').read_text()


def test_only_confidential_inference_router_is_mounted():
    forbidden = (
        "app.include_router(openai.router",
        "app.include_router(ollama.router",
        "app.include_router(chats.router",
        "app.include_router(files.router",
        "app.include_router(retrieval.router",
        "app.include_router(tools.router",
        "app.include_router(pipelines.router",
    )
    assert all(item not in MAIN for item in forbidden)
    assert "app.include_router(confidential.router" in MAIN


def test_plaintext_routes_are_rejected_before_body_processing():
    assert "class ConfidentialOnlyMiddleware" in MIDDLEWARE
    assert "'/api/v1/confidential'" in MIDDLEWARE
    assert "does not expose plaintext prompt or server transcript routes" in MIDDLEWARE


def test_open_webui_does_not_accept_a_ciphertext_relay():
    assert '@router.post("/relay/chat/completions")' not in CONFIDENTIAL_ROUTER
    assert 'relay_ciphertext' not in CONFIDENTIAL_ROUTER
    assert 'CONFIDENTIAL_MAX_CIPHERTEXT_BYTES' not in CONFIDENTIAL_ROUTER


def test_browser_confidential_transport_stays_direct_to_the_attested_api():
    assert 'relayFetch' not in CLIENT
    assert '/api/v1/confidential/relay' not in CLIENT
    assert 'fetchImpl: fetch' in CLIENT
