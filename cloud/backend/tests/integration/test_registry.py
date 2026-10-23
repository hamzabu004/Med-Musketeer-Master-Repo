"""TC-C07 and TC-C08: the system-admin registry API against the real database."""
import uuid

import pytest
from sqlalchemy import text

from app.auth import Principal
from tests.integration.test_schema import add_org, add_patient, add_user

pytestmark = pytest.mark.integration


def register_active_device(client, device_type: str = "wearable") -> str:
    device_id = str(uuid.uuid4())
    assert client.post("/admin/devices", json={"device_id": device_id, "type": device_type, "is_testbed": True}).status_code == 201
    credential = {"auth_method": "x509_mtls", "key_type": "ec_p256", "credential_ref": f"serial-{uuid.uuid4().hex}"}
    assert client.post(f"/admin/devices/{device_id}/credentials", json=credential).status_code == 201
    assert client.post(f"/admin/devices/{device_id}/activate").json()["status"] == "active"
    return device_id


def test_tc_c08_registry_round_trip(admin_client, system_admin):
    org = admin_client.post("/admin/organisations", json={"name": "Ward A", "kind": "public"})
    assert org.status_code == 201
    org_id = org.json()["org_id"]
    assert org.json()["registered_by"] == str(system_admin.user_id)
    assert [o["org_id"] for o in admin_client.get("/admin/organisations").json()] == [org_id]

    device_id = str(uuid.uuid4())
    created = admin_client.post("/admin/devices", json={"device_id": device_id, "type": "fixed_gateway", "is_testbed": False})
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    assert admin_client.post("/admin/devices", json={"device_id": device_id, "type": "wearable", "is_testbed": True}).status_code == 409

    # a device cannot be activated before it has a credential
    assert admin_client.post(f"/admin/devices/{device_id}/activate").status_code == 409
    credential = admin_client.post(f"/admin/devices/{device_id}/credentials", json={
        "auth_method": "x509_mtls", "key_type": "rsa_2048", "credential_ref": "serial-01", "metadata": {"cn": device_id},
    })
    assert credential.status_code == 201
    assert credential.json()["metadata"] == {"cn": device_id}
    assert admin_client.post(f"/admin/devices/{device_id}/activate").json()["status"] == "active"
    assert admin_client.post(f"/admin/devices/{device_id}/activate").status_code == 409  # already active
    assert admin_client.post(f"/admin/devices/{device_id}/suspend").json()["status"] == "suspended"
    assert admin_client.post(f"/admin/devices/{device_id}/activate").json()["status"] == "active"

    grant = admin_client.post(f"/admin/devices/{device_id}/grants", json={"org_id": org_id})
    assert grant.status_code == 201
    assert admin_client.post(f"/admin/devices/{device_id}/grants", json={"org_id": org_id}).status_code == 409
    assert len(admin_client.get(f"/admin/devices/{device_id}/grants").json()) == 1

    assert admin_client.patch(f"/admin/organisations/{org_id}", json={"status": "suspended"}).json()["status"] == "suspended"
    assert admin_client.get(f"/admin/devices/{device_id}").json()["type"] == "fixed_gateway"
    assert [d["device_id"] for d in admin_client.get("/admin/devices").json()] == [device_id]


def test_tc_c07_revoking_a_grant_ends_the_open_assignment_and_session(admin_client, system_admin, db):
    org_id = admin_client.post("/admin/organisations", json={"name": "Ward A", "kind": "public"}).json()["org_id"]
    device_id = register_active_device(admin_client)
    grant_id = admin_client.post(f"/admin/devices/{device_id}/grants", json={"org_id": org_id}).json()["grant_id"]
    org_admin = add_user(db, "org_admin", org_id)
    patient = add_patient(db, org_id)
    db.execute(text("INSERT INTO device_assignments (device_id, patient_id, issued_by) VALUES (:d, :p, :by)"),
               {"d": device_id, "p": patient, "by": org_admin})
    db.execute(text("INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path) VALUES (:d, :p, :o, 'fixed')"),
               {"d": device_id, "p": patient, "o": org_id})

    revoked = admin_client.post(f"/admin/grants/{grant_id}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_by"] == str(system_admin.user_id)
    assert db.scalar(text("SELECT count(*) FROM device_assignments WHERE device_id = :d AND unassigned_at IS NULL"), {"d": device_id}) == 0
    assert db.scalar(text("SELECT count(*) FROM monitoring_sessions WHERE device_id = :d AND ended_at IS NULL"), {"d": device_id}) == 0
    assert admin_client.post(f"/admin/grants/{grant_id}/revoke").status_code == 409


def test_revoking_a_device_revokes_its_credentials_and_closes_its_grant(admin_client, db):
    org_id = admin_client.post("/admin/organisations", json={"name": "Ward A", "kind": "public"}).json()["org_id"]
    device_id = register_active_device(admin_client)
    admin_client.post(f"/admin/devices/{device_id}/grants", json={"org_id": org_id})

    assert admin_client.post(f"/admin/devices/{device_id}/revoke").json()["status"] == "revoked"
    assert {c["status"] for c in admin_client.get(f"/admin/devices/{device_id}/credentials").json()} == {"revoked"}
    assert db.scalar(text("SELECT count(*) FROM device_grants WHERE device_id = :d AND revoked_at IS NULL"), {"d": device_id}) == 0
    # revoked is final
    for action in ("activate", "suspend", "revoke"):
        assert admin_client.post(f"/admin/devices/{device_id}/{action}").status_code == 409
    assert admin_client.post(f"/admin/devices/{device_id}/credentials",
                             json={"auth_method": "x509_mtls", "credential_ref": "new"}).status_code == 409


def test_grants_need_an_existing_active_organisation(admin_client):
    device_id = register_active_device(admin_client)
    assert admin_client.post(f"/admin/devices/{device_id}/grants", json={"org_id": str(uuid.uuid4())}).status_code == 404
    org_id = admin_client.post("/admin/organisations", json={"name": "Ward A", "kind": "public"}).json()["org_id"]
    admin_client.patch(f"/admin/organisations/{org_id}", json={"status": "suspended"})
    assert admin_client.post(f"/admin/devices/{device_id}/grants", json={"org_id": org_id}).status_code == 409


def test_unknown_records_return_404(admin_client):
    missing = uuid.uuid4()
    assert admin_client.get(f"/admin/devices/{missing}").status_code == 404
    assert admin_client.post(f"/admin/devices/{missing}/activate").status_code == 404
    assert admin_client.post(f"/admin/credentials/{missing}/revoke").status_code == 404
    assert admin_client.post(f"/admin/grants/{missing}/revoke").status_code == 404
    assert admin_client.patch(f"/admin/organisations/{missing}", json={"status": "active"}).status_code == 404


def test_registry_is_closed_until_authentication_exists(make_client):
    # No override: the production get_principal refuses every request until Slice 3.
    client = make_client(None)
    assert client.get("/admin/devices").status_code == 401
    assert client.post("/admin/organisations", json={"name": "x", "kind": "public"}).status_code == 401


@pytest.mark.parametrize("role", ["org_admin", "doctor", "patient"])
def test_registry_is_for_the_system_admin_only(make_client, db, role):
    org_id = add_org(db)
    user_id = add_user(db, role, org_id)
    client = make_client(Principal(user_id=user_id, role=role, org_id=org_id))
    assert client.get("/admin/devices").status_code == 403
    assert client.post("/admin/organisations", json={"name": "x", "kind": "public"}).status_code == 403
