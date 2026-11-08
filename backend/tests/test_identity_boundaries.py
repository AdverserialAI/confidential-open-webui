"""Behavioral regressions against real schemas, repositories and auth boundaries.

Only unrelated application imports are stubbed. Persistence uses real
SQLAlchemy async sessions and SQLite, not mocked CRUD/duplicate results.
"""
import ast
import asyncio
import importlib.util
import sys
import time
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import JSON, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

ROOT = Path(__file__).resolve().parents[1] / 'open_webui'
INVALID = [' victim@example.test', 'victim@example.test ', '\tvictim@example.test',
           'victim@example.test\r\n', '\u00a0victim@example.test', '\u200bvictim@example.test',
           'victim@example.test\u200f', '\ufeffvictim@example.test', 'victim@exam\x00ple.test',
           'victim@example.test extra', 'victim@example.test@other.test',
           '\uff56ictim@example.test', 'victim@\uff45xample.test', '\"victim\"@example.test']


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class IdentityBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        @asynccontextmanager
        async def context(db=None):
            if isinstance(db, AsyncSession):
                yield db
            else:
                async with factory() as session:
                    yield session
        Base = declarative_base()
        modules = {n: types.ModuleType(n) for n in [
            'open_webui','open_webui.models','open_webui.utils','open_webui.internal',
            'open_webui.env','open_webui.internal.db','open_webui.utils.misc','open_webui.utils.validate']}
        modules['open_webui.env'].DATABASE_USER_ACTIVE_STATUS_UPDATE_INTERVAL = 60
        modules['open_webui.internal.db'].Base = Base
        modules['open_webui.internal.db'].JSONField = JSON
        modules['open_webui.internal.db'].get_async_db_context = context
        modules['open_webui.utils.misc'].throttle = lambda *a, **k: lambda f: f
        modules['open_webui.utils.validate'].validate_profile_image_url = lambda v: v
        self.module_patch = patch.dict(sys.modules, modules)
        self.module_patch.start()
        self.identity = load('open_webui.utils.identity', ROOT/'utils/identity.py')
        self.users = load('open_webui.models.users', ROOT/'models/users.py')
        self.auths = load('open_webui.models.auths', ROOT/'models/auths.py')
        self.context = context
        async with self.engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        self.victim = await self.auths.Auths.insert_new_auth('victim@example.test','victim-password-hash','Victim',role='user')

    async def asyncTearDown(self):
        self.module_patch.stop()
        for n in ('open_webui.utils.identity','open_webui.models.users','open_webui.models.auths'):
            sys.modules.pop(n,None)
        await self.engine.dispose()

    async def test_signup_and_admin_forms_reject_whitespace_unicode_and_quoted_aliases(self):
        for email in INVALID:
            for form in (self.auths.SignupForm, self.auths.AddUserForm):
                with self.subTest(email=repr(email),form=form.__name__), self.assertRaises(ValueError):
                    form(email=email,password='test-password',name='Attacker')
            with self.subTest(email=repr(email)),self.assertRaises(ValueError):
                self.users.UserUpdateForm(email=email)

    async def test_persistence_rejects_invalid_identity_from_every_writer(self):
        for email in INVALID:
            with self.subTest(email=repr(email)):
                with self.assertRaises(ValueError):
                    await self.auths.Auths.insert_new_auth(email,'hash','Attacker',role='user')
                with self.assertRaises(ValueError):
                    await self.users.Users.insert_new_user('attacker-id','Attacker',email,role='user')
                with self.assertRaises(ValueError):
                    await self.auths.Auths.update_email_by_id(self.victim.id,email)
                with self.assertRaises(ValueError):
                    await self.users.Users.update_user_by_id(self.victim.id,{'email':email})
                self.assertIsNone(await self.users.Users.get_user_by_email(email))
        self.assertEqual((await self.users.Users.get_user_by_id(self.victim.id)).email,'victim@example.test')

    async def test_case_alias_cannot_create_a_second_account(self):
        with self.assertRaises(IntegrityError):
            await self.auths.Auths.insert_new_auth('VICTIM@EXAMPLE.TEST','attacker-hash','Attacker')
        self.assertEqual((await self.users.Users.get_user_by_email('VICTIM@EXAMPLE.TEST')).id,self.victim.id)

    async def test_plus_tags_and_dots_remain_separate_mailboxes(self):
        for email in ('victim+tag@example.test','vic.tim@example.test','jose\u00e9@example.test'):
            created=await self.auths.Auths.insert_new_auth(email,'hash','Other',role='user')
            self.assertNotEqual(created.id,self.victim.id)
            self.assertEqual(created.email,email)

    async def test_email_collision_cannot_partially_update_auth_record(self):
        other=await self.auths.Auths.insert_new_auth('other@example.test','hash','Other',role='user')
        with self.assertRaises(IntegrityError):
            await self.auths.Auths.update_email_by_id(other.id,'VICTIM@EXAMPLE.TEST')
        async with self.context() as c:
            self.assertEqual((await c.get(self.auths.Auth,other.id)).email,'other@example.test')
            self.assertEqual((await c.get(self.users.User,other.id)).email,'other@example.test')

    async def test_all_email_updates_keep_login_and_profile_identity_in_sync(self):
        await self.auths.Auths.update_email_by_id(self.victim.id,'new@example.test')
        await self.users.Users.update_user_by_id(self.victim.id,{'email':'final@example.test'})
        async with self.context() as c:
            self.assertEqual((await c.get(self.auths.Auth,self.victim.id)).email,'final@example.test')
            self.assertEqual((await c.get(self.users.User,self.victim.id)).email,'final@example.test')

    async def test_expired_or_disabled_api_credentials_cannot_authenticate(self):
        async with self.context() as c:
            for name,expiry in [('expired',int(time.time())-1),('valid',int(time.time())+60),('durable',None)]:
                c.add(self.users.ApiKey(id=name,key='sk-'+name,user_id=self.victim.id,expires_at=expiry,created_at=int(time.time()),updated_at=int(time.time())))
            await c.commit()
        self.assertIsNone(await self.users.Users.get_user_by_api_key('sk-expired'))
        self.assertEqual((await self.users.Users.get_user_by_api_key('sk-valid')).id,self.victim.id)
        async with self.context() as c:
            (await c.get(self.auths.Auth,self.victim.id)).active=False
            await c.commit()
        self.assertIsNone(await self.users.Users.get_user_by_api_key('sk-valid'))
        self.assertIsNone(await self.users.Users.get_user_by_api_key('sk-durable'))

    async def test_existing_bad_identity_or_disabled_account_cannot_refresh_a_session(self):
        # Compile the actual auth boundary independently of unrelated application imports.
        source=ast.parse((ROOT/'utils/auth.py').read_text())
        node=next(n for n in source.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='get_verified_user_by_token')
        async def valid(*a):return True
        state={'id':self.victim.id}
        namespace={'decode_token':lambda t:state,'is_valid_token':valid,'Users':self.users.Users,
                   'Auths':self.auths.Auths,'VERIFIED_USER_ROLES':{'user','admin'},
                   'valid_identity_email':self.identity.valid_identity_email}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'real-auth-boundary','exec'),namespace)
        resolve=namespace['get_verified_user_by_token']
        self.assertIsNotNone(await resolve('local-token'))
        async with self.context() as c:
            (await c.get(self.auths.Auth,self.victim.id)).active=False
            await c.commit()
        self.assertIsNone(await resolve('local-token'))
        async with self.context() as c:
            c.add(self.auths.Auth(id='legacy-twin',email=' victim@example.test',password='hash',active=True))
            c.add(self.users.User(id='legacy-twin',email=' victim@example.test',name='Legacy',role='user',created_at=1,updated_at=1,last_active_at=1))
            await c.commit()
        state['id']='legacy-twin'
        self.assertIsNone(await resolve('local-token'))

    async def test_oauth_linking_requires_boolean_verified_email(self):
        for flag in (None,False,'true','false',1,{},[]):
            self.assertFalse(self.identity.email_claim_is_verified({'email_verified':flag}))
        self.assertTrue(self.identity.email_claim_is_verified({'email_verified':True}))

    async def test_oauth_email_link_cannot_replace_an_existing_provider_identity(self):
        match=self.identity.oauth_binding_matches
        self.assertTrue(match(None,'google','new-sub'))
        self.assertTrue(match({'github':{'sub':'123'}},'google','new-sub'))
        self.assertTrue(match({'github':{'sub':123}},'github','123'))
        self.assertFalse(match({'google':{'sub':'existing-sub'}},'google','new-sub'))
        self.assertFalse(match({'google':{}},'google','new-sub'))


if __name__=='__main__':unittest.main()
