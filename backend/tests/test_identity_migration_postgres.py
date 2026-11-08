"""PostgreSQL identity-write guard; opt in with an isolated local database."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
import uuid

TEST_URL=os.environ.get('IDENTITY_TEST_DATABASE_URL')
if TEST_URL and urlparse(TEST_URL).hostname not in {'localhost','127.0.0.1'}:
    raise RuntimeError('Identity migration regression requires a local test database')

@unittest.skipUnless(TEST_URL,'Set IDENTITY_TEST_DATABASE_URL for PostgreSQL integration regression')
class IdentityMigration(unittest.TestCase):
    def test_database_migration_blocks_identity_write_variants_without_rewriting_legacy_rows(self):
        import psycopg
        path=Path(__file__).resolve().parents[1]/'open_webui/migrations/versions/a8f3c09d21e6_guard_email_identity_writes.py'
        spec=importlib.util.spec_from_file_location('identity_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        with psycopg.connect(TEST_URL) as c:
            schema='guard_'+uuid.uuid4().hex
            c.execute('CREATE SCHEMA '+schema);c.execute('SET LOCAL search_path TO '+schema)
            c.execute('CREATE TABLE "user"(id text,email text)');c.execute('CREATE TABLE auth(id text,email text,active boolean)')
            c.execute('INSERT INTO auth VALUES(\'legacy\',\' victim@example.test\',true)')
            adapter=SimpleNamespace(get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),execute=c.execute)
            with patch.object(migration,'op',adapter):migration.upgrade()
            for table in ['user','auth']:
                for pad in [' ','\t','\n','\u00a0','\u200b','\u200f','\ufeff']:
                    with self.subTest(table=table,pad=repr(pad)),self.assertRaises(psycopg.errors.CheckViolation):
                        with c.transaction():c.execute('INSERT INTO "'+table+'" (id,email) VALUES(%s,%s)',(str(uuid.uuid4()),pad+'victim@example.test'))
                c.execute('INSERT INTO "'+table+'" (id,email) VALUES(%s,%s)',('normal','normal@example.test'))
                with self.assertRaises(psycopg.errors.CheckViolation):
                    with c.transaction():c.execute('UPDATE "'+table+'" SET email=%s WHERE id=%s',(' normal@example.test','normal'))
            c.execute('UPDATE auth SET active=false WHERE id=\'legacy\'')
            self.assertEqual(c.execute('SELECT email,active FROM auth WHERE id=\'legacy\'').fetchone(),(' victim@example.test',False))
            c.rollback()

