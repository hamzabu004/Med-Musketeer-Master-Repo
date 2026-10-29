"""Revocation sync (Iteration 4, Slice 1, D16).

- revocation_state: one row. `version` goes up in the transaction of every registry change that
  alters the wearable revocation list; `published_version` is the last version EMQX accepted as
  the retained list. A version above it means the list still has to be published.
- devices.status_changed_at: when the device last changed status (the `since` of a listed
  wearable; the revocation time later backlog data is compared with). Existing rows start at
  created_at.
- devices.revocation_version: the list version a gateway last reported in its own status.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-29
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE revocation_state (
        singleton          boolean PRIMARY KEY DEFAULT true CHECK (singleton),
        version            bigint NOT NULL CHECK (version >= 1),
        published_version  bigint NOT NULL DEFAULT 0 CHECK (published_version <= version),
        published_at       timestamptz
    )
    """,
    # Version 1 is the empty list, so a new stack publishes a list that gateways can hold.
    "INSERT INTO revocation_state (version) VALUES (1)",
    "REVOKE INSERT, DELETE ON revocation_state FROM mm_api",
    "ALTER TABLE devices ADD COLUMN status_changed_at timestamptz",
    "UPDATE devices SET status_changed_at = created_at",
    "ALTER TABLE devices ALTER COLUMN status_changed_at SET NOT NULL",
    "ALTER TABLE devices ALTER COLUMN status_changed_at SET DEFAULT now()",
    "ALTER TABLE devices ADD COLUMN revocation_version bigint CHECK (revocation_version >= 0)",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE devices DROP COLUMN revocation_version")
    op.execute("ALTER TABLE devices DROP COLUMN status_changed_at")
    op.execute("DROP TABLE revocation_state")
