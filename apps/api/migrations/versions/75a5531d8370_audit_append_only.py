"""audit append only

Revision ID: 75a5531d8370
Revises: 585baa0d57f8
Create Date: 2026-11-11 14:27:42.490752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75a5531d8370'
down_revision: Union[str, Sequence[str], None] = '585baa0d57f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION forbid_audit_change() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER audit_no_change BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION forbid_audit_change();
    """)
    op.execute("""
        CREATE TRIGGER audit_no_truncate BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION forbid_audit_change();
    """)
    pass


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_no_change ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS forbid_audit_change()")
    pass