"""TC-C03 to TC-C06: the migrations and the rules the database itself enforces."""
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

REPORT_TABLES = {
    "organisations", "users", "patients", "care_assignments", "patient_disorders", "patient_exports",
    "devices", "device_grants", "device_assignments", "device_credentials", "device_updates",
    "monitoring_sessions", "ecg_segments", "ecg_chunks", "classifications", "alerts", "commands",
    "replay_windows", "security_events", "attack_tests",
}

ADDED_TABLES = {"audit_log", "ingested_messages"}  # D11, migration 0002; D15, migration 0003


def public_tables(conn) -> set[str]:
    return set(conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))


# --- arrangement helpers (as the schema owner) -------------------------------------------------

def add_org(db) -> uuid.UUID:
    return db.scalar(text("INSERT INTO organisations (name, kind) VALUES ('Ward A', 'public') RETURNING org_id"))


def add_user(db, role: str, org_id) -> uuid.UUID:
    return db.scalar(text("INSERT INTO users (zitadel_sub, role, org_id) VALUES (:sub, :role, :org) RETURNING user_id"),
                     {"sub": f"sub-{uuid.uuid4()}", "role": role, "org": org_id})


def add_patient(db, org_id) -> uuid.UUID:
    return db.scalar(text("INSERT INTO patients (org_id, pseudonym) VALUES (:org, :p) RETURNING patient_id"),
                     {"org": org_id, "p": f"P-{uuid.uuid4().hex[:6]}"})


def add_device(db, device_type: str = "wearable") -> uuid.UUID:
    return db.scalar(text("INSERT INTO devices (device_id, type, is_testbed) VALUES (:id, :type, true) RETURNING device_id"),
                     {"id": uuid.uuid4(), "type": device_type})


def assign(db, device_id, patient_id, issued_by, offset_s: int = 0):
    db.execute(text("""INSERT INTO device_assignments (device_id, assigned_at, patient_id, issued_by)
                       VALUES (:d, now() + make_interval(secs => :o), :p, :by)"""),
               {"d": device_id, "p": patient_id, "by": issued_by, "o": offset_s})


def violates(db, sql: str, params: dict, constraint: str):
    with pytest.raises(IntegrityError) as excinfo:
        db.execute(text(sql), params)
    assert excinfo.value.orig.diag.constraint_name == constraint


# --- TC-C03 ------------------------------------------------------------------------------------

def test_tc_c03_migrations_go_down_and_up_on_an_empty_database(migrated):
    config = alembic_config(migrated["migrator"])
    engine = create_engine(migrated["migrator"])
    try:
        command.downgrade(config, "base")
        with engine.connect() as conn:
            assert public_tables(conn) == {"alembic_version"}
        command.upgrade(config, "head")
        with engine.connect() as conn:
            assert public_tables(conn) == REPORT_TABLES | ADDED_TABLES | {"alembic_version"}
            hypertables = set(conn.scalars(text("SELECT hypertable_name FROM timescaledb_information.hypertables")))
            assert hypertables == {"ecg_chunks", "security_events"}
            retention = conn.execute(text(
                "SELECT hypertable_name, config->>'drop_after' FROM timescaledb_information.jobs "
                "WHERE proc_name = 'policy_retention'"
            )).all()
            assert [row[0] for row in retention] == ["ecg_chunks"]
            referencing_chunks = conn.scalar(text(
                "SELECT count(*) FROM pg_constraint WHERE contype = 'f' AND confrelid = 'ecg_chunks'::regclass"
            ))
            assert referencing_chunks == 0
    finally:
        engine.dispose()


def test_tc_c03_the_api_login_can_change_rows_but_not_the_schema(migrated, db):
    engine = create_engine(migrated["api"])
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO organisations (name, kind) VALUES ('Ward B', 'private')"))
        for statement in ("CREATE TABLE intruder (id int)", "DROP TABLE organisations",
                          "ALTER TABLE devices ADD COLUMN x int", "DELETE FROM alembic_version",
                          "UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log",
                          "UPDATE ingested_messages SET seq = 0", "DELETE FROM ingested_messages"):
            with engine.connect() as conn, pytest.raises(ProgrammingError):
                conn.execute(text(statement))
    finally:
        engine.dispose()


# --- TC-C04 to TC-C06 --------------------------------------------------------------------------

def test_tc_c04_a_device_has_at_most_one_open_grant(db, system_admin):
    device, org_a, org_b = add_device(db), add_org(db), add_org(db)
    sql = "INSERT INTO device_grants (device_id, org_id, granted_by) VALUES (:d, :o, :by)"
    db.execute(text(sql), {"d": device, "o": org_a, "by": system_admin.user_id})
    violates(db, sql, {"d": device, "o": org_b, "by": system_admin.user_id}, "device_grants_one_open")
    db.execute(text("UPDATE device_grants SET revoked_at = now(), revoked_by = :by"), {"by": system_admin.user_id})
    db.execute(text(sql), {"d": device, "o": org_b, "by": system_admin.user_id})  # allowed once the first is closed


def test_tc_c05_one_active_wearable_per_patient_and_one_patient_per_wearable(db):
    org = add_org(db)
    admin = add_user(db, "org_admin", org)
    patient_a, patient_b = add_patient(db, org), add_patient(db, org)
    wearable_1, wearable_2 = add_device(db), add_device(db)
    assign(db, wearable_1, patient_a, admin)
    sql = """INSERT INTO device_assignments (device_id, assigned_at, patient_id, issued_by)
             VALUES (:d, now() + interval '1 second', :p, :by)"""
    violates(db, sql, {"d": wearable_2, "p": patient_a, "by": admin}, "device_assignments_one_active_per_patient")
    violates(db, sql, {"d": wearable_1, "p": patient_b, "by": admin}, "device_assignments_one_active_per_device")


def test_tc_c06_one_active_doctor_per_patient(db):
    org = add_org(db)
    admin, doctor_1, doctor_2 = add_user(db, "org_admin", org), add_user(db, "doctor", org), add_user(db, "doctor", org)
    patient = add_patient(db, org)
    sql = "INSERT INTO care_assignments (patient_id, doctor_id, assigned_by) VALUES (:p, :d, :by)"
    db.execute(text(sql), {"p": patient, "d": doctor_1, "by": admin})
    violates(db, sql, {"p": patient, "d": doctor_2, "by": admin}, "care_assignments_one_active")


def test_a_monitoring_session_keeps_its_patient_and_organisation(db):
    org = add_org(db)
    patient_a, patient_b = add_patient(db, org), add_patient(db, org)
    device = add_device(db)
    session = db.scalar(text("""INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path)
                                VALUES (:d, :p, :o, 'fixed') RETURNING session_id"""),
                        {"d": device, "p": patient_a, "o": org})
    with pytest.raises(IntegrityError, match="fixed once opened"):
        db.execute(text("UPDATE monitoring_sessions SET patient_id = :p WHERE session_id = :s"),
                   {"p": patient_b, "s": session})
    db.execute(text("UPDATE monitoring_sessions SET ended_at = now() WHERE session_id = :s"), {"s": session})


def test_users_belong_to_an_organisation_except_the_system_admin(db):
    org = add_org(db)
    violates(db, "INSERT INTO users (zitadel_sub, role, org_id) VALUES ('x', 'system_admin', :o)", {"o": org},
             "users_org_matches_role")
    violates(db, "INSERT INTO users (zitadel_sub, role) VALUES ('y', 'doctor')", {}, "users_org_matches_role")


def test_a_recording_segment_needs_the_command_that_requested_it(db):
    org = add_org(db)
    patient, device = add_patient(db, org), add_device(db)
    session = db.scalar(text("""INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path)
                                VALUES (:d, :p, :o, 'fixed') RETURNING session_id"""),
                        {"d": device, "p": patient, "o": org})
    violates(db, """INSERT INTO ecg_segments (session_id, patient_id, device_id, kind, fs_hz, started_at)
                    VALUES (:s, :p, :d, 'recording', 360, now())""",
             {"s": session, "p": patient, "d": device}, "ecg_segments_recording_has_command")
