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
        refresh = AsyncMock()
        model_id = 'Adverserial/cyberseek'
        self.assertEqual(await resolve(model_id, self.request(model_id), refresh, None), model_id)
        refresh.assert_not_awaited()

    async def test_cyberseek_aliases_resolve_to_cyberseek(self):
        for model_id in ('cyberseek', 'CyberSeek', 'Adverserial/cyberseek'):
            self.assertEqual(await resolve(model_id, self.request('Adverserial/cyberseek'), AsyncMock(), None), 'Adverserial/cyberseek')

    async def test_legacy_models_and_browser_aliases_are_request_only(self):
        old_ids = ('lordx64/cyberkimi', 'lordx64/cyberglm', 'CyberKimi', 'cyberkimi',
                   'cyberglm', 'cyberglm-chat', 'CyberGLM')
        for old_id in old_ids:
            refresh = AsyncMock()
            with self.assertRaisesRegex(ValueError, 'available only on request'):
                await resolve(old_id, self.request(old_id, 'Adverserial/cyberseek'), refresh, None)
            refresh.assert_not_awaited()

    async def test_nonempty_stale_registry_refreshes_on_missing_model(self):
        request = self.request('lordx64/cyberkimi')
        user = object()
        async def update(req, **kwargs):
            req.app.state.MODELS['Adverserial/cyberseek'] = {}
        refresh = AsyncMock(side_effect=update)
        self.assertEqual(await resolve('cyberseek', request, refresh, user), 'Adverserial/cyberseek')
        refresh.assert_awaited_once_with(request, refresh=True, user=user)

    async def test_unknown_model_fails_after_one_refresh(self):
        refresh = AsyncMock()
        with self.assertRaisesRegex(ValueError, 'Model not found'):
            await resolve('unknown-model', self.request('Adverserial/cyberseek'), refresh, None)
        refresh.assert_awaited_once()

    async def test_other_configured_models_keep_their_ids(self):
        self.assertEqual(await resolve('other/model', self.request('other/model'), AsyncMock(), None), 'other/model')


class PublicCatalogTests(unittest.TestCase):
    def test_legacy_models_and_aliases_are_hidden(self):
        models = [{'id': 'cyberglm'}, {'id': 'lordx64/cyberglm'}, {'id': 'lordx64/cyberkimi'},
                  {'id': 'cyberseek'}, {'id': 'Adverserial/cyberseek'}]
        self.assertEqual([m['id'] for m in module.public_model_catalog(models)], ['Adverserial/cyberseek'])
        self.assertEqual(len(models), 5)

    def test_unrelated_models_are_preserved(self):
        self.assertEqual(module.public_model_catalog([{'id': 'another/model'}]), [{'id': 'another/model'}])


if __name__ == '__main__':
    unittest.main()
