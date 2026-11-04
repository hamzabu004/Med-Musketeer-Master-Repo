"""Gateway connectivity (D17).

- connectivity_events: a gateway's connections to the cloud, and its wearables' presence through
  it. One row per change of state of a device on a gateway (the gateway's own rows have
  device_id = gateway_id), so the newest row's `at` is when the current state began: a gateway's
  uptime. Ingestion appends only; the API may not change or delete rows.
- alerts.gateway_id: the gateway that attested the alert (D1); null for alerts stored before this
  revision and, later, for the mobile path. The org admin's gateway view lists alert times by it.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-30
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE connectivity_events (
        event_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id    uuid NOT NULL REFERENCES devices (device_id),
        gateway_id   uuid NOT NULL REFERENCES devices (device_id),
        state        text NOT NULL CHECK (state IN ('online', 'offline')),
        reason       text,
        at           timestamptz NOT NULL,  -- the broker's receive time
        recorded_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX connectivity_events_gateway_at ON connectivity_events (gateway_id, at DESC)",
    "CREATE INDEX connectivity_events_device_at ON connectivity_events (device_id, gateway_id, at DESC)",
    "REVOKE UPDATE, DELETE ON connectivity_events FROM mm_api",
    "ALTER TABLE alerts ADD COLUMN gateway_id uuid REFERENCES devices (device_id)",
    "CREATE INDEX alerts_gateway_created ON alerts (gateway_id, created_at DESC)",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE alerts DROP COLUMN gateway_id")
    op.execute("DROP TABLE connectivity_events")
