"""Account status and the audit log (Slice 3 part 2, D11).

- users.status: an organisation admin disables a doctor or patient account; a disabled user's
  tokens are refused at once, without waiting for ZITADEL's tokens to expire.
- audit_log: every registry and organisation action with the acting user, the organisation and
  the target. The API may only append to it.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    ALTER TABLE users ADD COLUMN status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled'))
    """,
    """
    CREATE TABLE audit_log (
        event_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        at         timestamptz NOT NULL DEFAULT now(),
        actor_id   uuid NOT NULL REFERENCES users (user_id),
        -- registry: system-admin actions (devices, grants, organisations), shown to the system admin;
        -- organisation: an organisation admin's actions, shown to that organisation's admins
        scope      text NOT NULL CHECK (scope IN ('registry', 'organisation')),
        org_id     uuid REFERENCES organisations (org_id),
        action     text NOT NULL,
        target_id  uuid,
        details    jsonb NOT NULL DEFAULT '{}'::jsonb,
        CHECK (scope = 'registry' OR org_id IS NOT NULL)
    )
    """,
    "CREATE INDEX audit_log_scope_org_at ON audit_log (scope, org_id, at)",
    # Append-only for the API (the default privileges from 0001 granted it all four).
    "REVOKE UPDATE, DELETE ON audit_log FROM mm_api",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE audit_log")
    op.execute("ALTER TABLE users DROP COLUMN status")
