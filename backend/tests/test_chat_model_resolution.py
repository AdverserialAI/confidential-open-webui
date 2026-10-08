import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec = importlib.util.spec_from_file_location(
    'chat_model_resolution',
    Path(__file__).parents[1] / 'open_webui/utils/chat_model_resolution.py',
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
resolve = module.resolve_chat_model_id


class ModelResolutionTests(unittest.IsolatedAsyncioTestCase):
    def request(self, *ids):
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(MODELS={i: {} for i in ids})))

    async def test_current_canonical_model_needs_no_refresh(self):
        for model_id in ('lordx64/cyberkimi', 'lordx64/cyberglm'):
            refresh = AsyncMock()
            self.assertEqual(await resolve(model_id, self.request(model_id), refresh, None), model_id)
            refresh.assert_not_awaited()

    async def test_legacy_glm_browser_selections_resolve_to_glm(self):
        for old_id in ('cyberglm', 'cyberglm-chat', 'CyberGLM'):
            self.assertEqual(await resolve(old_id, self.request('lordx64/cyberglm'), AsyncMock(), None), 'lordx64/cyberglm')

    async def test_kimi_aliases_resolve_to_kimi(self):
        for old_id in ('CyberKimi', 'cyberkimi'):
            self.assertEqual(await resolve(old_id, self.request('lordx64/cyberkimi'), AsyncMock(), None), 'lordx64/cyberkimi')

    async def test_nonempty_stale_registry_refreshes_on_missing_model(self):
        request = self.request('lordx64/cyberkimi')
        user = object()
        async def update(req, **kwargs):
            req.app.state.MODELS['lordx64/cyberglm'] = {}
        refresh = AsyncMock(side_effect=update)
        self.assertEqual(await resolve('cyberglm-chat', request, refresh, user), 'lordx64/cyberglm')
        refresh.assert_awaited_once_with(request, refresh=True, user=user)

    async def test_unknown_model_fails_after_one_refresh(self):
        refresh = AsyncMock()
        with self.assertRaisesRegex(ValueError, 'Model not found'):
            await resolve('unknown-model', self.request('lordx64/cyberkimi'), refresh, None)
        refresh.assert_awaited_once()

    async def test_missing_glm_does_not_fall_back_to_kimi(self):
        with self.assertRaisesRegex(ValueError, 'Model not found'):
            await resolve('CyberGLM', self.request('lordx64/cyberkimi'), AsyncMock(), None)

    async def test_other_configured_models_keep_their_ids(self):
        self.assertEqual(await resolve('other/model', self.request('other/model'), AsyncMock(), None), 'other/model')


class PublicCatalogTests(unittest.TestCase):
    def test_alias_hidden_without_removing_runtime_base(self):
        models = [{'id': 'cyberglm'}, {'id': 'lordx64/cyberglm'}, {'id': 'lordx64/cyberkimi'}]
        self.assertEqual([m['id'] for m in module.public_model_catalog(models)], ['lordx64/cyberglm', 'lordx64/cyberkimi'])
        self.assertEqual(models[0]['id'], 'cyberglm')
        self.assertEqual(len(models), 3)

    def test_alias_visible_when_canonical_model_is_not_accessible(self):
        self.assertEqual(module.public_model_catalog([{'id': 'cyberglm'}]), [{'id': 'cyberglm'}])

    def test_unrelated_models_are_preserved(self):
        self.assertEqual(module.public_model_catalog([{'id': 'another/model'}]), [{'id': 'another/model'}])


if __name__ == '__main__':
    unittest.main()
