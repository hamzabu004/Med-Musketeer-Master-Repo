"""TC-C09 to TC-C11: who may call what, and whose data they get (D9).

TC-C09 calls every endpoint as every role on a fresh populated database (tests.integration.world):
an allowed role must succeed (2xx) on a target it is entitled to, a denied role must get 403.
Every route of the app must appear in MATRIX, so a new endpoint cannot ship without its row.
TC-C10 and TC-C11 check the data boundaries within the allowed calls: other doctors' and other
organisations' patients answer 404 and never appear in lists; the system admin gets no patient
or doctor data.
"""
import json
import re
import uuid

import pytest

from app.main import create_app
from app.settings import Settings
from tests.integration.world import World, build_world

pytestmark = pytest.mark.integration

ROLES = ("system_admin", "org_admin", "doctor", "patient")
SA, OA, DR, PT = ROLES
PUBLIC = {("GET", "/livez"), ("GET", "/healthz"), ("GET", "/me")}  # /me: every authenticated role

# (method, path, allowed roles, body). Paths and bodies may use the World's fields, e.g. {a.patient_id}.
MATRIX = [
    # registry (system admin)
    ("GET", "/admin/organisations", {SA}, None),
    ("POST", "/admin/organisations", {SA}, {"name": "New org", "kind": "private"}),
    ("PATCH", "/admin/organisations/{a.org_id}", {SA}, {"status": "active"}),
    ("POST", "/admin/organisations/{a.org_id}/admins", {SA},
     {"email": "admin2@a.example", "given_name": "Ada", "family_name": "Admin"}),
    ("GET", "/admin/devices", {SA}, None),
    ("POST", "/admin/devices", {SA}, {"device_id": "{new_id}", "type": "wearable", "is_testbed": True}),
    ("GET", "/admin/devices/{a.wearable}", {SA}, None),
    ("POST", "/admin/devices/{pending_device}/activate", {SA}, None),
    ("POST", "/admin/devices/{a.wearable}/suspend", {SA}, None),
    ("POST", "/admin/devices/{a.wearable}/revoke", {SA}, None),
    ("POST", "/admin/devices/{pending_device}/credentials", {SA}, {"auth_method": "x509_mtls", "credential_ref": "s-2"}),
    ("GET", "/admin/devices/{a.wearable}/credentials", {SA}, None),
    ("POST", "/admin/credentials/{credential}/revoke", {SA}, None),
    ("POST", "/admin/devices/{pending_device}/grants", {SA}, {"org_id": "{a.org_id}"}),
    ("GET", "/admin/devices/{a.wearable}/grants", {SA}, None),
    ("POST", "/admin/grants/{grant}/revoke", {SA}, None),
    ("GET", "/admin/audit", {SA}, None),
    ("GET", "/admin/security-events", {SA}, None),
    # own organisation
    ("GET", "/organisation", {OA, DR, PT}, None),
    ("GET", "/devices", {OA, DR}, None),
    ("GET", "/audit", {OA}, None),
    # accounts (organisation admin)
    ("GET", "/accounts", {OA}, None),
    ("POST", "/accounts", {OA}, {"role": "doctor", "email": "doc@a.example", "given_name": "Dee", "family_name": "Doc"}),
    ("POST", "/accounts/{spare_doctor}/disable", {OA}, None),
    # patients
    ("GET", "/patients", {OA, DR}, None),
    ("PUT", "/patients/{spare_patient}/doctor", {OA}, {"doctor_id": "{spare_doctor}"}),
    ("POST", "/patients/{spare_patient}/wearable", {OA}, {"device_id": "{spare_wearable}"}),
    ("DELETE", "/patients/{a.patient_id}/wearable", {OA}, None),
    ("GET", "/patients/{a.patient_id}/disorders", {OA, DR}, None),
    ("POST", "/patients/{a.patient_id}/disorders", {OA}, {"disorder": "atrial fibrillation"}),
    ("POST", "/patients/{a.patient_id}/exports", {OA}, {"destination": "referral to clinic B"}),
    # ECG, classifications, alerts (doctor: own patients; patient: self)
    ("GET", "/alerts", {DR, PT}, None),
    ("GET", "/patients/{a.patient_id}/alerts", {DR, PT}, None),
    ("POST", "/alerts/{a.alert}/acknowledge", {DR}, None),
    ("GET", "/patients/{a.patient_id}/segments", {DR, PT}, None),
    ("GET", "/segments/{a.segment}", {DR, PT}, None),
]
# D9 rows without an endpoint yet: on-demand ECG (gap: start/stop design), attack tests (Iteration 5).


def fill(template, world: World):
    if template is None:
        return None
    if isinstance(template, dict):
        return {key: fill(value, world) for key, value in template.items()}
    if isinstance(template, str):
        return template.format(**vars(world), new_id=uuid.uuid4())
    return template


@pytest.fixture
def world(db) -> World:
    return build_world(db)


def call(client, method: str, path: str, body=None):
    return client.request(method, path, json=body)


def all_operations() -> set[tuple[str, str]]:
    settings = Settings(database_url="postgresql+psycopg://u:p@127.0.0.1:1/db", zitadel_url="http://127.0.0.1:1",
                        emqx_status_url="http://127.0.0.1:1/status")
    paths = create_app(settings).openapi()["paths"]
    return {(method.upper(), shape(path)) for path, operations in paths.items() for method in operations}


def shape(path: str) -> str:
    """/patients/{a.patient_id}/alerts and /patients/{patient_id}/alerts -> /patients/{}/alerts"""
    return re.sub(r"\{[^}]+\}", "{}", path)


# --- TC-C09 ------------------------------------------------------------------------------------

def test_tc_c09_the_matrix_covers_every_endpoint():
    rows = [(method, shape(path)) for method, path, _, _ in MATRIX]
    assert len(rows) == len(set(rows)), "duplicate matrix rows"
    assert set(rows) | PUBLIC == all_operations()


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("method,path,allowed,body", MATRIX, ids=[f"{m} {p}" for m, p, _, _ in MATRIX])
def test_tc_c09_role_endpoint_matrix(make_client, world, role, method, path, allowed, body):
    client = make_client(world.principal(role))
    response = call(client, method, fill(path, world), fill(body, world))
    if role in allowed:
        assert 200 <= response.status_code < 300, response.text
    else:
        assert response.status_code == 403, response.text


# --- TC-C10 ------------------------------------------------------------------------------------

def ids_in(response) -> str:
    assert response.status_code == 200, response.text
    return response.text


@pytest.mark.parametrize("target", ["other doctor's patient", "other organisation's patient"])
def test_tc_c10_a_doctor_cannot_read_a_patient_who_is_not_theirs(make_client, world, target):
    doctor = make_client(world.a.doctor)
    patient, segment, alert = {
        "other doctor's patient": (world.a.other_patient_id, world.a.other_segment, world.a.other_alert),
        "other organisation's patient": (world.b.patient_id, world.b.segment, world.b.alert),
    }[target]
    for path in (f"/patients/{patient}/alerts", f"/patients/{patient}/segments",
                 f"/patients/{patient}/disorders", f"/segments/{segment}"):
        assert doctor.get(path).status_code == 404, path
    assert doctor.post(f"/alerts/{alert}/acknowledge").status_code == 404
    for path in ("/patients", "/alerts", "/devices"):
        body = ids_in(doctor.get(path))
        assert str(patient) not in body and str(alert) not in body, path
    # their own patient is visible
    assert str(world.a.patient_id) in ids_in(doctor.get("/patients"))


def test_tc_c10_a_doctor_loses_access_when_the_patient_gets_another_doctor(make_client, world):
    admin, doctor = make_client(world.a.admin), make_client(world.a.doctor)
    assert doctor.get(f"/patients/{world.a.patient_id}/alerts").status_code == 200
    reassigned = admin.put(f"/patients/{world.a.patient_id}/doctor", json={"doctor_id": str(world.a.other_doctor.user_id)})
    assert reassigned.status_code == 200
    assert doctor.get(f"/patients/{world.a.patient_id}/alerts").status_code == 404
    assert make_client(world.a.other_doctor).get(f"/patients/{world.a.patient_id}/alerts").status_code == 200


def test_tc_c10_a_patient_reads_only_their_own_data(make_client, world):
    patient = make_client(world.a.patient)
    assert patient.get(f"/patients/{world.a.patient_id}/alerts").status_code == 200
    for other, segment in ((world.a.other_patient_id, world.a.other_segment), (world.b.patient_id, world.b.segment)):
        assert patient.get(f"/patients/{other}/alerts").status_code == 404
        assert patient.get(f"/patients/{other}/segments").status_code == 404
        assert patient.get(f"/segments/{segment}").status_code == 404
    alerts = ids_in(patient.get("/alerts"))
    assert str(world.a.alert) in alerts and str(world.a.other_alert) not in alerts


def test_tc_c10_an_org_admin_cannot_reach_another_organisation(make_client, world):
    admin = make_client(world.a.admin)
    other = world.b.patient_id
    assert admin.get(f"/patients/{other}/disorders").status_code == 404
    assert admin.post(f"/patients/{other}/disorders", json={"disorder": "x"}).status_code == 404
    assert admin.put(f"/patients/{other}/doctor", json={"doctor_id": str(world.b.doctor.user_id)}).status_code == 404
    assert admin.put(f"/patients/{world.a.patient_id}/doctor",
                     json={"doctor_id": str(world.b.doctor.user_id)}).status_code == 404  # B's doctor
    assert admin.post(f"/patients/{world.spare_patient}/wearable",
                      json={"device_id": str(world.b.wearable)}).status_code == 404  # granted to B
    assert admin.post(f"/accounts/{world.b.doctor.user_id}/disable").status_code == 404
    assert admin.post(f"/patients/{other}/exports", json={"destination": "x"}).status_code == 404
    for path in ("/patients", "/accounts", "/devices", "/audit"):
        body = ids_in(admin.get(path))
        assert not any(secret in body for secret in world.b.secrets), path


def test_tc_c10_an_org_admin_reads_no_ecg_and_exports_without_it(make_client, world):
    admin = make_client(world.a.admin)
    export = admin.post(f"/patients/{world.a.patient_id}/exports", json={"destination": "referral"})
    assert export.status_code == 201
    assert export.json()["ecg_included"] is False
    assert str(world.a.segment) not in export.text and str(world.a.alert) not in export.text


# --- TC-C11 ------------------------------------------------------------------------------------

def test_tc_c11_the_system_admin_gets_no_patient_or_doctor_data(make_client, world):
    # Organisation-side actions first, so the audit log holds patient and doctor ids.
    org_admin = make_client(world.a.admin)
    assert org_admin.put(f"/patients/{world.spare_patient}/doctor", json={"doctor_id": str(world.spare_doctor)}).status_code == 200
    assert org_admin.post(f"/patients/{world.spare_patient}/wearable", json={"device_id": str(world.spare_wearable)}).status_code == 201
    assert org_admin.post("/accounts", json={"role": "patient", "email": "pat@a.example", "given_name": "Pat",
                                             "family_name": "Ient", "pseudonym": "P-new"}).status_code == 201
    secrets = world.a.secrets | world.b.secrets | {str(world.spare_patient), str(world.spare_doctor), "P-new", "P-spare"}

    admin = make_client(world.system_admin)
    assert admin.post(f"/admin/grants/{world.grant}/revoke").status_code == 200  # ends the spare patient's wearable
    devices = [str(world.a.wearable), str(world.b.wearable)]
    paths = ["/admin/organisations", "/admin/devices", "/admin/audit", "/admin/security-events",
             *(f"/admin/devices/{d}" for d in devices), *(f"/admin/devices/{d}/grants" for d in devices),
             *(f"/admin/devices/{d}/credentials" for d in devices)]
    for path in paths:
        body = ids_in(admin.get(path))
        leaked = [secret for secret in secrets if secret in body]
        assert not leaked, (path, leaked)
    # and every endpoint outside /admin refuses the system admin
    for method, path, _, body in MATRIX:
        if not path.startswith("/admin"):
            assert call(admin, method, fill(path, world), fill(body, world)).status_code == 403, path
    assert "patient_id" not in json.dumps(admin.get("/admin/devices").json()[0])
