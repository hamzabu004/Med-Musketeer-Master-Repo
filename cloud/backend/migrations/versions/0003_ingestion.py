"""Ingestion (Slice 5, D15).

- ingested_messages: one row per stored device message that carries a msg_id (alerts, IDS
  events). Its key makes a QoS 1 redelivery a no-op, and its hop times are the latency record of
  each message (D7). The API may only append to it.
- ecg_segments.lead: the ECG lead the wearable recorded (alert-payload-v1).
- alerts.severity may be null, and nothing sets it: the wearable gives a label and a confidence, and
  the cloud does not rate alerts. The column stays because it is in the report's schema.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-29
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

UPGRADE = [
    """
    CREATE TABLE ingested_messages (
        device_id    uuid NOT NULL REFERENCES devices (device_id),
        msg_id       uuid NOT NULL,
        msg_type     text NOT NULL,
        seq          bigint,
        attested_by  uuid REFERENCES devices (device_id),
        sent_at      timestamptz,  -- device clock, benchmark only
        broker_at    timestamptz NOT NULL,
        adapter_at   timestamptz NOT NULL,
        ingested_at  timestamptz NOT NULL DEFAULT now(),
        -- scoped to the device, so one device cannot pre-empt another's message ids
        PRIMARY KEY (device_id, msg_id)
    )
    """,
    "REVOKE UPDATE, DELETE ON ingested_messages FROM mm_api",
    "ALTER TABLE ecg_segments ADD COLUMN lead text",
    "ALTER TABLE alerts ALTER COLUMN severity DROP NOT NULL",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("UPDATE alerts SET severity = 'unrated' WHERE severity IS NULL")
    op.execute("ALTER TABLE alerts ALTER COLUMN severity SET NOT NULL")
    op.execute("ALTER TABLE ecg_segments DROP COLUMN lead")
    op.execute("DROP TABLE ingested_messages")
