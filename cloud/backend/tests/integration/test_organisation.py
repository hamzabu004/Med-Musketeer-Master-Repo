"""The organisation-admin API against the real database, with ZITADEL's management API faked
(the real one is covered by TC-C13 in test_stack): accounts, doctor assignment, wearables,
disorders, exports, and the audit log."""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from tests.integration.world import World, build_world

pytestmark = pytest.mark.integration

DOCTOR = {"role": "doctor", "email": "dee@a.example", "given_name": "Dee", "family_name": "Doc"}
PATIENT = {"role": "patient", "email": "pat@a.example", "given_name": "Pat", "family_name": "Ient", "pseudonym": "P-100"}


@pytest.fixture
def world(db) -> World:
    return build_world(db)


@pytest.fixture
def admin(make_client, world):
    return make_client(world.a.admin)


def audit_actions(db, org_id) -> list[str]:
    return list(db.scalars(text("SELECT action FROM audit_log WHERE org_id = :o ORDER BY at, action"), {"o": org_id}))


# --- accounts ----------------------------------------------------------------------------------

def test_creating_accounts_registers_them_in_zitadel_and_the_database(admin, world, zitadel, db):
    doctor = admin.post("/accounts", json=DOCTOR)
    patient = admin.post("/accounts", json=PATIENT)
    assert doctor.status_code == 201 and patient.status_code == 201
    for response, role in ((doctor, "doctor"), (patient, "patient")):
        body = response.json()
        assert body["role"] == role and body["status"] == "active" and body["org_id"] == str(world.a.org_id)
        assert body["invite_code"] == f"INVITE-{body['zitadel_sub']}"
        zitadel_org = db.scalar(text("SELECT zitadel_org_id FROM organisations WHERE org_id = :o"), {"o": world.a.org_id})
        assert zitadel.users[body["zitadel_sub"]] == {"org": zitadel_org, "role": role,
                                                      "email": DOCTOR["email"] if role == "doctor" else PATIENT["email"],
                                                      "state": "active"}
    assert patient.json()["pseudonym"] == "P-100" and patient.json()["patient_id"]
    listed = {account["user_id"] for account in admin.get("/accounts").json()}
    assert {doctor.json()["user_id"], patient.json()["user_id"]} <= listed
    assert "invite_code" not in admin.get("/accounts").text
    assert audit_actions(db, world.a.org_id).count("account.created") == 2


@pytest.mark.parametrize("body,status", [
    ({**DOCTOR, "pseudonym": "P-1"}, 422),            # a doctor has no pseudonym
    ({**PATIENT, "pseudonym": None}, 422),            # a patient needs one
    ({**DOCTOR, "role": "org_admin"}, 422),           # only the system admin creates org admins
    ({**DOCTOR, "email": "not-an-email"}, 422),
])
def test_invalid_account_requests_are_refused_before_zitadel(admin, zitadel, body, status):
    assert admin.post("/accounts", json=body).status_code == status
    assert zitadel.users == {}


def test_a_zitadel_failure_leaves_no_rows(admin, zitadel, db):
    before = db.scalar(text("SELECT count(*) FROM users"))
    zitadel.fail("create_user", 503)
    assert admin.post("/accounts", json=DOCTOR).status_code == 502
    zitadel.fail("create_user", 409, "User already exists")
    assert admin.post("/accounts", json=DOCTOR).status_code == 409
    assert db.scalar(text("SELECT count(*) FROM users")) == before


def test_a_database_refusal_deletes_the_zitadel_user_again(admin, world, zitadel, db):
    # The pseudonym check runs before ZITADEL; a row that appears in between hits the unique key.
    db.execute(text("""
        CREATE FUNCTION test_take_pseudonym() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO patients (org_id, pseudonym) VALUES (NEW.org_id, 'P-100');
            RETURN NEW;
        END $$
    """))
    db.execute(text("CREATE TRIGGER test_take_pseudonym BEFORE INSERT ON users FOR EACH ROW "
                    "WHEN (NEW.role = 'patient') EXECUTE FUNCTION test_take_pseudonym()"))
    try:
        assert admin.post("/accounts", json=PATIENT).status_code == 409
        assert zitadel.users == {}
    finally:
        db.execute(text("DROP TRIGGER test_take_pseudonym ON users"))
        db.execute(text("DROP FUNCTION test_take_pseudonym()"))


def test_a_pseudonym_is_unique_in_the_organisation(admin, zitadel):
    assert admin.post("/accounts", json=PATIENT).status_code == 201
    assert admin.post("/accounts", json={**PATIENT, "email": "other@a.example"}).status_code == 409
    assert len(zitadel.users) == 1


def test_disabling_a_doctor_ends_their_care_assignments(admin, world, zitadel, db):
    sub = db.scalar(text("SELECT zitadel_sub FROM users WHERE user_id = :u"), {"u": world.a.doctor.user_id})
    zitadel.users[sub] = {"state": "active"}
    response = admin.post(f"/accounts/{world.a.doctor.user_id}/disable")
    assert response.status_code == 200 and response.json()["status"] == "disabled"
    assert zitadel.users[sub]["state"] == "inactive"
    assert db.scalar(text("SELECT count(*) FROM care_assignments WHERE doctor_id = :u AND valid_to IS NULL"),
                     {"u": world.a.doctor.user_id}) == 0
    assert admin.post(f"/accounts/{world.a.doctor.user_id}/disable").status_code == 409
    # a disabled doctor cannot be assigned again
    assert admin.put(f"/patients/{world.a.patient_id}/doctor",
                     json={"doctor_id": str(world.a.doctor.user_id)}).status_code == 404


def test_disabling_a_patient_returns_their_wearable(admin, world, zitadel, db):
    sub = db.scalar(text("SELECT zitadel_sub FROM users WHERE user_id = :u"), {"u": world.a.patient.user_id})
    zitadel.users[sub] = {"state": "active"}
    assert admin.post(f"/accounts/{world.a.patient.user_id}/disable").status_code == 200
    assert db.scalar(text("SELECT count(*) FROM device_assignments WHERE patient_id = :p AND unassigned_at IS NULL"),
                     {"p": world.a.patient_id}) == 0
    assert db.scalar(text("SELECT count(*) FROM monitoring_sessions WHERE patient_id = :p AND ended_at IS NULL"),
                     {"p": world.a.patient_id}) == 0
    assert admin.post(f"/patients/{world.a.patient_id}/wearable",
                      json={"device_id": str(world.spare_wearable)}).status_code == 409


def test_a_zitadel_failure_keeps_the_account_enabled(admin, world, zitadel, db):
    zitadel.fail("deactivate_user", 503)
    assert admin.post(f"/accounts/{world.a.doctor.user_id}/disable").status_code == 502
    assert db.scalar(text("SELECT status FROM users WHERE user_id = :u"), {"u": world.a.doctor.user_id}) == "active"
    assert "account.disabled" not in audit_actions(db, world.a.org_id)


def test_org_admins_and_other_organisations_accounts_cannot_be_disabled(admin, world):
    assert admin.post(f"/accounts/{world.a.admin.user_id}/disable").status_code == 404
    assert admin.post(f"/accounts/{world.b.doctor.user_id}/disable").status_code == 404


# --- doctors, wearables, disorders, exports ----------------------------------------------------

def test_assigning_a_doctor_replaces_the_previous_one(admin, world, db):
    first = admin.put(f"/patients/{world.spare_patient}/doctor", json={"doctor_id": str(world.spare_doctor)})
    assert first.status_code == 200
    again = admin.put(f"/patients/{world.spare_patient}/doctor", json={"doctor_id": str(world.spare_doctor)})
    assert again.json()["assignment_id"] == first.json()["assignment_id"]  # unchanged
    second = admin.put(f"/patients/{world.spare_patient}/doctor", json={"doctor_id": str(world.a.doctor.user_id)})
    assert second.json()["assignment_id"] != first.json()["assignment_id"]
    rows = db.execute(text("SELECT doctor_id, valid_to IS NULL AS open FROM care_assignments WHERE patient_id = :p "
                           "ORDER BY valid_from"), {"p": world.spare_patient}).all()
    assert [(row.doctor_id, row.open) for row in rows] == [(world.spare_doctor, False), (world.a.doctor.user_id, True)]
    # only a doctor of the organisation can be assigned
    assert admin.put(f"/patients/{world.spare_patient}/doctor",
                     json={"doctor_id": str(world.a.admin.user_id)}).status_code == 404


def test_issuing_and_returning_a_wearable(admin, world, make_client, db):
    issued = admin.post(f"/patients/{world.spare_patient}/wearable", json={"device_id": str(world.spare_wearable)})
    assert issued.status_code == 201 and issued.json()["issued_by"] == str(world.a.admin.user_id)
    # one wearable per patient, one patient per wearable
    assert admin.post(f"/patients/{world.spare_patient}/wearable", json={"device_id": str(world.a.wearable)}).status_code == 409
    assert admin.post(f"/patients/{world.a.patient_id}/wearable", json={"device_id": str(world.spare_wearable)}).status_code == 409
    returned = admin.delete(f"/patients/{world.spare_patient}/wearable")
    assert returned.status_code == 200 and returned.json()["unassigned_at"] is not None
    assert admin.delete(f"/patients/{world.spare_patient}/wearable").status_code == 404
    assert audit_actions(db, world.a.org_id)[-2:] == ["wearable.issued", "wearable.returned"]


def test_only_an_active_wearable_granted_to_the_organisation_can_be_issued(admin, world, make_client):
    system_admin = make_client(world.system_admin)
    assert admin.post(f"/patients/{world.spare_patient}/wearable",
                      json={"device_id": str(world.pending_device)}).status_code == 404  # not granted
    assert system_admin.post(f"/admin/devices/{world.spare_wearable}/suspend").status_code == 200
    assert admin.post(f"/patients/{world.spare_patient}/wearable",
                      json={"device_id": str(world.spare_wearable)}).status_code == 409
    gateway = system_admin.post("/admin/devices", json={"device_id": "00000000-0000-4000-8000-000000000001",
                                                        "type": "fixed_gateway", "is_testbed": True}).json()["device_id"]
    system_admin.post(f"/admin/devices/{gateway}/credentials", json={"auth_method": "x509_mtls", "credential_ref": "AB" * 32})
    system_admin.post(f"/admin/devices/{gateway}/activate")
    system_admin.post(f"/admin/devices/{gateway}/grants", json={"org_id": str(world.a.org_id)})
    assert admin.post(f"/patients/{world.spare_patient}/wearable", json={"device_id": gateway}).status_code == 422
    assert gateway in admin.get("/devices").text  # the org admin sees the organisation's gateways


def test_disorders_and_exports_are_recorded_with_the_acting_user(admin, world, make_client, db):
    recorded = admin.post(f"/patients/{world.a.patient_id}/disorders", json={"disorder": "atrial fibrillation"})
    assert recorded.status_code == 201 and recorded.json()["recorded_by"] == str(world.a.admin.user_id)
    assert admin.post(f"/patients/{world.a.patient_id}/disorders", json={"disorder": "atrial fibrillation"}).status_code == 409
    doctor_view = make_client(world.a.doctor).get(f"/patients/{world.a.patient_id}/disorders").json()
    assert "atrial fibrillation" in {row["disorder"] for row in doctor_view}

    export = admin.post(f"/patients/{world.a.patient_id}/exports", json={"destination": "referral to clinic B"})
    assert export.status_code == 201
    body = export.json()
    assert body["exported_by"] == str(world.a.admin.user_id)
    assert {row["disorder"] for row in body["disorders"]} >= {"atrial fibrillation"}
    assert body["wearable_assignments"][0]["device_id"] == str(world.a.wearable)
    assert db.scalar(text("SELECT destination FROM patient_exports WHERE export_id = :e"),
                     {"e": body["export_id"]}) == "referral to clinic B"
    events = admin.get("/audit").json()
    assert [event["action"] for event in events[:2]] == ["patient.exported", "disorder.recorded"]
    assert all(event["actor_id"] == str(world.a.admin.user_id) for event in events[:2])


# --- doctor and patient views ------------------------------------------------------------------

def test_a_doctor_acknowledges_an_alert_once(make_client, world):
    doctor = make_client(world.a.doctor)
    assert [a["alert_id"] for a in doctor.get("/alerts?unacknowledged=true").json()] == [str(world.a.alert)]
    acknowledged = doctor.post(f"/alerts/{world.a.alert}/acknowledge")
    assert acknowledged.status_code == 200
    assert acknowledged.json()["acknowledged_by"] == str(world.a.doctor.user_id)
    assert acknowledged.json()["label"] == "abnormal"
    assert doctor.post(f"/alerts/{world.a.alert}/acknowledge").status_code == 409
    assert doctor.get("/alerts?unacknowledged=true").json() == []


def test_a_segment_comes_with_its_samples_and_classification(make_client, world):
    segment = make_client(world.a.patient).get(f"/segments/{world.a.segment}").json()
    assert segment["chunks"] == [{"seq": 0, "ts": segment["chunks"][0]["ts"], "n_samples": 2,
                                  "encoding": "int16le-base64", "samples": "AQACAA=="}]
    assert segment["classifications"][0]["label"] == "abnormal"


# --- organisations and their admins (system admin) ---------------------------------------------

def test_an_organisation_and_its_admin_are_created_in_zitadel(make_client, world, zitadel, db):
    system_admin = make_client(world.system_admin)
    org = system_admin.post("/admin/organisations", json={"name": "Clinic C", "kind": "private"})
    assert org.status_code == 201
    zitadel_org = org.json()["zitadel_org_id"]
    assert zitadel.organisations[zitadel_org] == "Clinic C"
    org_admin = system_admin.post(f"/admin/organisations/{org.json()['org_id']}/admins",
                                  json={"email": "ada@c.example", "given_name": "Ada", "family_name": "Admin"})
    assert org_admin.status_code == 201 and org_admin.json()["role"] == "org_admin"
    assert zitadel.users[org_admin.json()["zitadel_sub"]]["org"] == zitadel_org
    actions = {row.action for row in db.execute(text("SELECT action FROM audit_log WHERE scope = 'registry'"))}
    assert {"organisation.created", "account.created"} <= actions


def test_a_zitadel_failure_creates_no_organisation(make_client, world, zitadel, db):
    system_admin = make_client(world.system_admin)
    zitadel.fail("create_organisation", 503)
    assert system_admin.post("/admin/organisations", json={"name": "Clinic C", "kind": "private"}).status_code == 502
    assert db.scalar(text("SELECT count(*) FROM organisations WHERE name = 'Clinic C'")) == 0


def test_an_organisation_admin_needs_an_active_organisation_with_a_zitadel_organisation(make_client, world, db):
    system_admin = make_client(world.system_admin)
    person = {"email": "ada@a.example", "given_name": "Ada", "family_name": "Admin"}
    legacy = db.scalar(text("INSERT INTO organisations (name, kind) VALUES ('Legacy', 'public') RETURNING org_id"))
    assert system_admin.post(f"/admin/organisations/{legacy}/admins", json=person).status_code == 409
    system_admin.patch(f"/admin/organisations/{world.a.org_id}", json={"status": "suspended"})
    assert system_admin.post(f"/admin/organisations/{world.a.org_id}/admins", json=person).status_code == 409


# --- concurrent changes (review findings 1 and 2, 2026-10-24) ----------------------------------

@pytest.fixture
def concurrent(owner_engine):
    """Run `request` while another transaction holds `change` uncommitted: the request must wait
    for that transaction's row locks, and then see the committed change."""
    executor = ThreadPoolExecutor(max_workers=1)

    def run(change: str, params: dict, request):
        with owner_engine.connect() as conn:
            transaction = conn.begin()
            conn.execute(text(change), params)
            future = executor.submit(request)
            deadline = time.monotonic() + 10
            while not waiting_on_a_lock(owner_engine):
                assert not future.done(), f"the request did not wait: {future.result().status_code}"
                assert time.monotonic() < deadline, "the request never blocked"
                time.sleep(0.05)
            transaction.commit()
        return future.result(timeout=10)

    yield run
    executor.shutdown()


def waiting_on_a_lock(engine) -> bool:
    # pg_locks, not pg_stat_activity: the owner may not see the wait events of mm_api's sessions.
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM pg_locks WHERE NOT granted")) > 0


def test_issuing_a_wearable_waits_for_a_concurrent_grant_revoke(admin, world, concurrent, db):
    response = concurrent(
        "UPDATE device_grants SET revoked_at = now(), revoked_by = :by WHERE grant_id = :g",
        {"by": world.system_admin.user_id, "g": world.grant},
        lambda: admin.post(f"/patients/{world.spare_patient}/wearable", json={"device_id": str(world.spare_wearable)}),
    )
    assert response.status_code == 404  # no longer granted to the organisation
    assert db.scalar(text("SELECT count(*) FROM device_assignments WHERE device_id = :d"), {"d": world.spare_wearable}) == 0


def test_issuing_a_wearable_waits_for_a_concurrent_patient_disable(admin, world, concurrent, db):
    db.execute(text("DELETE FROM device_assignments WHERE patient_id = :p"), {"p": world.a.patient_id})
    response = concurrent(
        "UPDATE users SET status = 'disabled' WHERE user_id = :u", {"u": world.a.patient.user_id},
        lambda: admin.post(f"/patients/{world.a.patient_id}/wearable", json={"device_id": str(world.spare_wearable)}),
    )
    assert response.status_code == 409
    assert db.scalar(text("SELECT count(*) FROM device_assignments WHERE patient_id = :p"), {"p": world.a.patient_id}) == 0


def test_assigning_a_doctor_waits_for_a_concurrent_doctor_disable(admin, world, concurrent, db):
    response = concurrent(
        "UPDATE users SET status = 'disabled' WHERE user_id = :u", {"u": world.spare_doctor},
        lambda: admin.put(f"/patients/{world.spare_patient}/doctor", json={"doctor_id": str(world.spare_doctor)}),
    )
    assert response.status_code == 404  # no active doctor of that id any more
    assert db.scalar(text("SELECT count(*) FROM care_assignments WHERE doctor_id = :d"), {"d": world.spare_doctor}) == 0
