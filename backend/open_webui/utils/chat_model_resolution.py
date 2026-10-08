"""Resolve public chat model IDs without relying on a dyno's stale registry."""

# Preserve selections saved by older browser sessions while exposing canonical
# IDs to API clients. Never substitute one model family for another.
MODEL_ID_ALIASES = {
    'cyberkimi': 'lordx64/cyberkimi',
    'CyberKimi': 'lordx64/cyberkimi',
    'cyberglm': 'lordx64/cyberglm',
    'CyberGLM': 'lordx64/cyberglm',
    'cyberglm-chat': 'lordx64/cyberglm',
}


async def resolve_chat_model_id(model_id, request, refresh_models, user):
    resolved_id = MODEL_ID_ALIASES.get(model_id, model_id)
    if resolved_id not in request.app.state.MODELS:
        # Workspace model updates can reach a different dyno from the next
        # completion. Refresh once on a miss, even if the registry is nonempty.
        await refresh_models(request, refresh=True, user=user)
    if resolved_id not in request.app.state.MODELS:
        raise ValueError('Model not found')
    return resolved_id


def public_model_catalog(models):
    """Hide superseded aliases in listings, without disabling provider models.

    Workspace presets still need their native base models in the runtime
    registry. Filtering belongs in the public catalog, not model activation.
    """
    ids = {model['id'] for model in models}
    return [
        model for model in models
        if MODEL_ID_ALIASES.get(model['id']) not in ids
    ]
