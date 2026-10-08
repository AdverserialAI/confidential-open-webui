from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / 'open_webui' / 'main.py').read_text()
MIDDLEWARE = (ROOT / 'open_webui' / 'utils' / 'asgi_middleware.py').read_text()


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
