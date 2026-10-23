"""Initial cloud schema (mid report §5 "Cloud schema", plus organisations.zitadel_org_id from D3).

Rules enforced by the database:
- at most one open grant per device                        (device_grants_one_open)
- one active wearable per patient, one patient per device  (device_assignments_one_active_*)
- one active doctor per patient                             (care_assignments_one_active)
- one open monitoring session per device; a session's device, patient, organisation and path
  never change once it is opened                            (monitoring_sessions_immutable)
- ecg_chunks and security_events are hypertables on ts; raw ecg_chunks are dropped after the
  retention period, and no foreign key points into ecg_chunks

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Placeholder until the team fixes the raw-ECG retention period (gaps.md).
ECG_CHUNK_RETENTION = "90 days"

UPGRADE = [
    # --- people and organisations -------------------------------------------------------------
    """
    CREATE TABLE organisations (
        org_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        name            text NOT NULL,
        kind            text NOT NULL CHECK (kind IN ('public', 'private')),
        status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
        zitadel_org_id  text UNIQUE,
        registered_by   uuid,
        created_at      timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE users (
        user_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        zitadel_sub  text NOT NULL UNIQUE,
        role         text NOT NULL CHECK (role IN ('system_admin', 'org_admin', 'doctor', 'patient')),
        org_id       uuid REFERENCES organisations (org_id),
        created_at   timestamptz NOT NULL DEFAULT now(),
        -- the system admin stands outside every organisation; everyone else belongs to one
        CONSTRAINT users_org_matches_role CHECK ((role = 'system_admin') = (org_id IS NULL))
    )
    """,
    "ALTER TABLE organisations ADD FOREIGN KEY (registered_by) REFERENCES users (user_id)",
    """
    CREATE TABLE patients (
        patient_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id     uuid UNIQUE REFERENCES users (user_id),
        org_id      uuid NOT NULL REFERENCES organisations (org_id),
        pseudonym   text NOT NULL,
        created_at  timestamptz NOT NULL DEFAULT now(),
        UNIQUE (org_id, pseudonym)
    )
    """,
    """
    CREATE TABLE care_assignments (
        assignment_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id      uuid NOT NULL REFERENCES patients (patient_id),
        doctor_id       uuid NOT NULL REFERENCES users (user_id),
        assigned_by     uuid NOT NULL REFERENCES users (user_id),
        recommended_at  timestamptz,
        valid_from      timestamptz NOT NULL DEFAULT now(),
        valid_to        timestamptz,
        CHECK (valid_to IS NULL OR valid_to >= valid_from)
    )
    """,
    "CREATE UNIQUE INDEX care_assignments_one_active ON care_assignments (patient_id) WHERE valid_to IS NULL",
    """
    CREATE TABLE patient_disorders (
        patient_id   uuid NOT NULL REFERENCES patients (patient_id),
        disorder     text NOT NULL,
        recorded_by  uuid NOT NULL REFERENCES users (user_id),
        recorded_at  timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (patient_id, disorder)
    )
    """,
    """
    CREATE TABLE patient_exports (
        export_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        patient_id   uuid NOT NULL REFERENCES patients (patient_id),
        exported_by  uuid NOT NULL REFERENCES users (user_id),
        destination  text NOT NULL,
        created_at   timestamptz NOT NULL DEFAULT now()
    )
    """,
    # --- devices -------------------------------------------------------------------------------
    """
    CREATE TABLE devices (
        device_id           uuid PRIMARY KEY,  -- equals the certificate CN
        type                text NOT NULL CHECK (type IN ('wearable', 'fixed_gateway')),
        status              text NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'active', 'suspended', 'revoked')),
        is_testbed          boolean NOT NULL,
        current_mode        text NOT NULL DEFAULT 'unknown' CHECK (current_mode IN ('fixed', 'mobile', 'unknown')),
        current_gateway_id  uuid REFERENCES devices (device_id),
        last_seen           timestamptz,
        registered_by       uuid REFERENCES users (user_id),
        created_at          timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE device_grants (
        grant_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id   uuid NOT NULL REFERENCES devices (device_id),
        org_id      uuid NOT NULL REFERENCES organisations (org_id),
        granted_by  uuid NOT NULL REFERENCES users (user_id),
        granted_at  timestamptz NOT NULL DEFAULT now(),
        revoked_by  uuid REFERENCES users (user_id),
        revoked_at  timestamptz,
        CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
    )
    """,
    "CREATE UNIQUE INDEX device_grants_one_open ON device_grants (device_id) WHERE revoked_at IS NULL",
    """
    CREATE TABLE device_assignments (
        device_id       uuid NOT NULL REFERENCES devices (device_id),
        assigned_at     timestamptz NOT NULL DEFAULT now(),
        patient_id      uuid NOT NULL REFERENCES patients (patient_id),
        issued_by       uuid NOT NULL REFERENCES users (user_id),
        recommended_by  uuid REFERENCES users (user_id),
        unassigned_at   timestamptz,
        PRIMARY KEY (device_id, assigned_at),
        CHECK (unassigned_at IS NULL OR unassigned_at >= assigned_at)
    )
    """,
    "CREATE UNIQUE INDEX device_assignments_one_active_per_device ON device_assignments (device_id) WHERE unassigned_at IS NULL",
    "CREATE UNIQUE INDEX device_assignments_one_active_per_patient ON device_assignments (patient_id) WHERE unassigned_at IS NULL",
    """
    CREATE TABLE device_credentials (
        credential_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id       uuid NOT NULL REFERENCES devices (device_id),
        auth_method     text NOT NULL,
        key_type        text,
        credential_ref  text NOT NULL,
        status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked', 'expired')),
        created_at      timestamptz NOT NULL DEFAULT now(),
        expires_at      timestamptz,
        metadata        jsonb NOT NULL DEFAULT '{}'::jsonb,
        UNIQUE (auth_method, credential_ref)
    )
    """,
    "CREATE INDEX device_credentials_device ON device_credentials (device_id)",
    """
    CREATE TABLE device_updates (
        update_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id     uuid NOT NULL REFERENCES devices (device_id),
        from_version  text,
        to_version    text NOT NULL,
        performed_by  uuid REFERENCES users (user_id),
        outcome       text NOT NULL,
        created_at    timestamptz NOT NULL DEFAULT now()
    )
    """,
    # --- ECG and alerts ------------------------------------------------------------------------
    """
    CREATE TABLE monitoring_sessions (
        session_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id   uuid NOT NULL REFERENCES devices (device_id),
        patient_id  uuid NOT NULL REFERENCES patients (patient_id),
        org_id      uuid NOT NULL REFERENCES organisations (org_id),
        path        text NOT NULL CHECK (path IN ('fixed', 'mobile')),
        started_at  timestamptz NOT NULL DEFAULT now(),
        ended_at    timestamptz,
        CHECK (ended_at IS NULL OR ended_at >= started_at)
    )
    """,
    "CREATE UNIQUE INDEX monitoring_sessions_one_open ON monitoring_sessions (device_id) WHERE ended_at IS NULL",
    """
    CREATE FUNCTION monitoring_sessions_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.device_id <> OLD.device_id OR NEW.patient_id <> OLD.patient_id
           OR NEW.org_id <> OLD.org_id OR NEW.path <> OLD.path OR NEW.started_at <> OLD.started_at THEN
            RAISE EXCEPTION 'monitoring session % is fixed once opened; only ended_at may change', OLD.session_id
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END $$
    """,
    """
    CREATE TRIGGER monitoring_sessions_immutable BEFORE UPDATE ON monitoring_sessions
        FOR EACH ROW EXECUTE FUNCTION monitoring_sessions_immutable()
    """,
    """
    CREATE TABLE commands (
        command_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id   uuid NOT NULL REFERENCES devices (device_id),
        issued_by   uuid NOT NULL REFERENCES users (user_id),
        type        text NOT NULL,
        path        text NOT NULL CHECK (path IN ('fixed', 'mobile')),
        counter     bigint,
        status      text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'acked', 'expired')),
        created_at  timestamptz NOT NULL DEFAULT now(),
        acked_at    timestamptz
    )
    """,
    """
    CREATE TABLE ecg_segments (
        segment_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id  uuid NOT NULL REFERENCES monitoring_sessions (session_id),
        patient_id  uuid NOT NULL REFERENCES patients (patient_id),
        device_id   uuid NOT NULL REFERENCES devices (device_id),
        kind        text NOT NULL CHECK (kind IN ('alert', 'recording')),
        command_id  uuid REFERENCES commands (command_id),
        fs_hz       smallint NOT NULL CHECK (fs_hz > 0),
        started_at  timestamptz NOT NULL,
        ended_at    timestamptz,
        CONSTRAINT ecg_segments_recording_has_command CHECK (kind <> 'recording' OR command_id IS NOT NULL)
    )
    """,
    """
    CREATE TABLE ecg_chunks (
        segment_id   uuid NOT NULL REFERENCES ecg_segments (segment_id),
        seq          integer NOT NULL,
        ts           timestamptz NOT NULL,
        n_samples    integer NOT NULL CHECK (n_samples > 0),
        samples      bytea NOT NULL,
        attested_by  uuid REFERENCES devices (device_id),
        auth_method  text NOT NULL,
        PRIMARY KEY (segment_id, seq, ts)
    )
    """,
    "SELECT create_hypertable('ecg_chunks', by_range('ts'))",
    f"SELECT add_retention_policy('ecg_chunks', INTERVAL '{ECG_CHUNK_RETENTION}')",
    """
    CREATE TABLE classifications (
        classification_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        segment_id         uuid NOT NULL REFERENCES ecg_segments (segment_id),
        source             text NOT NULL CHECK (source IN ('wearable', 'gateway', 'cloud')),
        model_version      text NOT NULL,
        label              text NOT NULL,
        confidence         real CHECK (confidence BETWEEN 0 AND 1),
        created_at         timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE alerts (
        alert_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        device_id          uuid NOT NULL REFERENCES devices (device_id),
        patient_id         uuid NOT NULL REFERENCES patients (patient_id),
        classification_id  uuid REFERENCES classifications (classification_id),
        origin             text NOT NULL,
        severity           text NOT NULL,
        created_at         timestamptz NOT NULL DEFAULT now(),
        acknowledged_by    uuid REFERENCES users (user_id),
        acknowledged_at    timestamptz,
        CHECK ((acknowledged_at IS NULL) = (acknowledged_by IS NULL))
    )
    """,
    # --- security ------------------------------------------------------------------------------
    """
    CREATE TABLE replay_windows (
        device_id        uuid NOT NULL REFERENCES devices (device_id),
        direction        text NOT NULL CHECK (direction IN ('up', 'down')),
        key_epoch        integer NOT NULL,
        highest_counter  bigint NOT NULL,
        bitmap           bit(64) NOT NULL DEFAULT B'0'::bit(64),
        PRIMARY KEY (device_id, direction, key_epoch)
    )
    """,
    """
    CREATE TABLE security_events (
        event_id         uuid NOT NULL DEFAULT gen_random_uuid(),
        ts               timestamptz NOT NULL,
        gateway_id       uuid NOT NULL REFERENCES devices (device_id),
        device_id        uuid REFERENCES devices (device_id),
        mode             text NOT NULL CHECK (mode IN ('ids', 'ips')),
        predicted_class  text NOT NULL,
        outcome          text NOT NULL,
        action           text,
        action_result    text,
        PRIMARY KEY (event_id, ts)
    )
    """,
    "SELECT create_hypertable('security_events', by_range('ts'))",
    """
    CREATE TABLE attack_tests (
        test_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        target_device_id  uuid NOT NULL REFERENCES devices (device_id),
        triggered_by      uuid NOT NULL REFERENCES users (user_id),
        attack_type       text NOT NULL,
        parameters        jsonb NOT NULL DEFAULT '{}'::jsonb,
        started_at        timestamptz NOT NULL DEFAULT now(),
        ended_at          timestamptz,
        CHECK (ended_at IS NULL OR ended_at >= started_at)
    )
    """,
    # --- runtime privileges: the API reads and writes rows, never changes the schema -----------
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mm_api",
    "REVOKE ALL ON alembic_version FROM mm_api",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mm_api",
]

TABLES = [
    "attack_tests", "security_events", "replay_windows", "alerts", "classifications", "ecg_chunks",
    "ecg_segments", "commands", "monitoring_sessions", "device_updates", "device_credentials",
    "device_assignments", "device_grants", "devices", "patient_exports", "patient_disorders",
    "care_assignments", "patients",
]


def upgrade() -> None:
    for statement in UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM mm_api")
    for table in TABLES:
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION monitoring_sessions_immutable()")
    op.execute("ALTER TABLE organisations DROP CONSTRAINT organisations_registered_by_fkey")
    op.execute("DROP TABLE users")
    op.execute("DROP TABLE organisations")
