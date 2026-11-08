"""Reject ambiguous identities on insert and email update without rewriting evidence.

Revision ID: a8f3c09d21e6
Revises: d4c1a8e37b62
"""
from alembic import op

revision = 'a8f3c09d21e6'
down_revision = 'd4c1a8e37b62'
branch_labels = None
depends_on = None

# Keep legacy malformed rows intact for incident review. Only inserting a new
# identity or changing an identity field invokes this guard; quarantining a
# legacy account does not rewrite or merge its email into a victim's account.
EMAIL_TRIGGER_FUNCTION_SQL = r'''
CREATE OR REPLACE FUNCTION reject_ambiguous_identity_email() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.email IS NOT NULL AND (
    length(NEW.email) > 254 OR
    position('@' in NEW.email)=0 OR
    NEW.email ~ '[[:space:][:cntrl:]]' OR
    NEW.email ~ U&'[\0001-\0020\007F-\009F\00A0\00AD\061C\1680\180E\2000-\200F\2028-\202F\205F-\206F\3000\FEFF\FFF9-\FFFB]' OR
    length(NEW.email)-length(replace(NEW.email, '@', '')) <> 1
  ) THEN
    RAISE EXCEPTION 'Invalid account email' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$$
'''


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute(EMAIL_TRIGGER_FUNCTION_SQL)
        for table in ('user', 'auth'):
            op.execute(f'DROP TRIGGER IF EXISTS guard_identity_email ON "{table}"')
            op.execute(f'CREATE TRIGGER guard_identity_email BEFORE INSERT OR UPDATE OF email ON "{table}" FOR EACH ROW EXECUTE FUNCTION reject_ambiguous_identity_email()')
    elif bind.dialect.name == 'sqlite':
        for table in ('user', 'auth'):
            for action, suffix in [('INSERT', 'insert'), ('UPDATE OF email', 'update')]:
                op.execute(f'''CREATE TRIGGER IF NOT EXISTS guard_{table}_email_{suffix}
                BEFORE {action} ON "{table}"
                WHEN NEW.email IS NOT NULL AND (
                  length(NEW.email)>254 OR NEW.email GLOB '*[ ' || char(9,10,11,12,13) || ']*' OR
                  instr(NEW.email,char(160))>0 OR instr(NEW.email,char(8203))>0 OR instr(NEW.email,char(65279))>0 OR
                  length(NEW.email)-length(replace(NEW.email,'@',''))<>1)
                BEGIN SELECT RAISE(ABORT, 'Invalid account email'); END''')


def downgrade():
    bind = op.get_bind()
    for table in ('user', 'auth'):
        if bind.dialect.name == 'postgresql':
            op.execute(f'DROP TRIGGER IF EXISTS guard_identity_email ON "{table}"')
        elif bind.dialect.name == 'sqlite':
            for suffix in ('insert', 'update'):
                op.execute(f'DROP TRIGGER IF EXISTS guard_{table}_email_{suffix}')
    if bind.dialect.name == 'postgresql':
        op.execute('DROP FUNCTION IF EXISTS reject_ambiguous_identity_email()')
