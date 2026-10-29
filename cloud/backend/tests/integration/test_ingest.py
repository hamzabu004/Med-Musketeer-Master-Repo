"""TC-C20 to TC-C26 at the API: ingest-v1 messages against the real database (D7, D15). The same
flow from a gateway through EMQX and the adapter is in test_ingestion (full stack)."""
import base64
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.auth import Principal
from tests.integration.world import insert, make_device, make_user
from tests.messages import alert_payload, ecg_samples, encode, ids_payload, ingest, status_payload

pytestmark = pytest.mark.integration

SECRET = "ingest-secret-for-tests-0123456789"
ADAPTER = {"Authorization": f"Bearer {SECRET}"}
TABLES = ("ecg_segments", "ecg_chunks", "classifications", "alerts", "monitoring_sessions", "ingested_messages",
          "security_events")


@pytest.fixture
def api(make_client):
    return make_client(None, ingest_secret=SECRET)


class Ward:
    """An organisation with an org admin, a doctor, two patients, a gateway, and a wearable
    issued to the first patient."""

    def __init__(self, db, system_admin: Principal):
        self.db = db
        self.org_id = insert(db, "INSERT INTO organisations (name, kind) VALUES ('Ward', 'public') RETURNING org_id")
        self.admin = Principal(make_user(db, "org_admin", self.org_id), "org_admin", self.org_id)
        self.doctor = Principal(make_user(db, "doctor", self.org_id), "doctor", self.org_id)
        self.patient_id, self.other_patient_id = (self.patient(), self.patient())
        self.gateway = make_device(db, "fixed_gateway", self.org_id, system_admin.user_id)
        self.wearable = make_device(db, "wearable", self.org_id, system_admin.user_id)
        self.issue(self.wearable, self.patient_id)

    def patient(self):
        patient_id = insert(self.db, "INSERT INTO patients (org_id, pseudonym) VALUES (:o, :p) RETURNING patient_id",
                            o=self.org_id, p=f"P-{uuid.uuid4().hex[:6]}")
        insert(self.db, "INSERT INTO care_assignments (patient_id, doctor_id, assigned_by) VALUES (:p, :d, :by) RETURNING 1",
               p=patient_id, d=self.doctor.user_id, by=self.admin.user_id)
        return patient_id

    def issue(self, wearable, patient_id):
        insert(self.db, "INSERT INTO device_assignments (device_id, patient_id, issued_by) VALUES (:d, :p, :by) RETURNING 1",
               d=wearable, p=patient_id, by=self.admin.user_id)

    def device(self, device_id) -> dict:
        return dict(self.db.execute(text("SELECT * FROM devices WHERE device_id = :d"), {"d": device_id}).mappings().one())


@pytest.fixture
def ward(db, system_admin) -> Ward:
    return Ward(db, system_admin)


def counts(db) -> dict[str, int]:
    return {table: db.scalar(text(f"SELECT count(*) FROM {table}")) for table in TABLES}


def post(api, body: dict, expected: int = 200) -> dict:
    response = api.post("/internal/ingest", json=body, headers=ADAPTER)
    assert response.status_code == expected, response.text
    return response.json()


def rejected(api, body: dict) -> str:
    return post(api, body, 422)["detail"]["rejected"]


# --- TC-C20 ------------------------------------------------------------------------------------

def test_tc_c20_an_alert_for_an_issued_wearable_lands_in_every_table(api, make_client, db, ward):
    listener = db.connection.driver_connection
    listener.execute("LISTEN mm_alerts")
    payload = alert_payload()
    message = ingest(ward.wearable, ward.gateway, "alert", payload)
    stored = post(api, message)
    assert stored["result"] == "stored"

    segment = db.execute(text("SELECT * FROM ecg_segments WHERE segment_id = :g"), {"g": stored["segment_id"]}).mappings().one()
    assert (segment["patient_id"], segment["device_id"], segment["kind"], segment["fs_hz"], segment["lead"]) == (
        ward.patient_id, ward.wearable, "alert", 360, "MLII")
    assert segment["started_at"] == datetime.fromisoformat(payload["segment_start"])
    assert segment["ended_at"] - segment["started_at"] == timedelta(seconds=3)
    chunk = db.execute(text("SELECT * FROM ecg_chunks WHERE segment_id = :g"), {"g": segment["segment_id"]}).mappings().one()
    assert chunk["attested_by"] == ward.gateway and chunk["auth_method"] == "x509_mtls"  # D1: the broker's word
    assert bytes(chunk["samples"]) == base64.b64decode(payload["samples"]) and chunk["n_samples"] == 1080
    session = db.execute(text("SELECT * FROM monitoring_sessions WHERE session_id = :s"),
                         {"s": stored["session_id"]}).mappings().one()
    assert (session["patient_id"], session["org_id"], session["path"], session["ended_at"]) == (
        ward.patient_id, ward.org_id, "fixed", None)
    alert = db.execute(text("""SELECT a.*, c.source, c.label, c.confidence, c.model_version FROM alerts a
                               JOIN classifications c USING (classification_id) WHERE a.alert_id = :a"""),
                       {"a": stored["alert_id"]}).mappings().one()
    assert (alert["patient_id"], alert["origin"], alert["severity"], alert["acknowledged_at"]) == (
        ward.patient_id, "wearable", None, None)  # the cloud does not rate alerts
    assert (alert["source"], alert["label"], alert["model_version"]) == ("wearable", "abnormal", "tinydl-0.1")
    hops = db.execute(text("SELECT * FROM ingested_messages")).mappings().one()
    assert (str(hops["msg_id"]), hops["seq"], hops["attested_by"]) == (payload["msg_id"], 7, ward.gateway)
    assert hops["sent_at"] < hops["broker_at"] < hops["adapter_at"] <= hops["ingested_at"]

    wearable = ward.device(ward.wearable)
    assert (wearable["current_mode"], wearable["current_gateway_id"]) == ("fixed", ward.gateway)
    assert wearable["last_seen"] == ward.device(ward.gateway)["last_seen"] == datetime.fromisoformat(message["received_at"])
    notice = next(listener.notifies(timeout=5, stop_after=1))
    assert notice.channel == "mm_alerts" and stored["alert_id"] in notice.payload

    # The doctor reads it through the care API, sample for sample.
    doctor = make_client(ward.doctor)
    assert [a["alert_id"] for a in doctor.get("/alerts").json()] == [stored["alert_id"]]
    assert "severity" not in doctor.get("/alerts").json()[0]
    detail = doctor.get(f"/segments/{stored['segment_id']}").json()
    assert detail["lead"] == "MLII" and detail["chunks"][0]["samples"] == encode(ecg_samples(1080))


def test_ingestion_needs_the_adapters_secret(make_client, ward):
    body = ingest(ward.wearable, ward.gateway, "alert", alert_payload())
    assert make_client(None).post("/internal/ingest", json=body, headers=ADAPTER).status_code == 503  # not configured
    api = make_client(None, ingest_secret=SECRET)
    assert api.post("/internal/ingest", json=body).status_code == 401
    assert api.post("/internal/ingest", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401


# --- TC-C21 ------------------------------------------------------------------------------------

def test_tc_c21_an_alert_for_an_unissued_wearable_is_rejected_and_logged(api, db, ward, system_admin, caplog):
    spare = make_device(db, "wearable", ward.org_id, system_admin.user_id)
    before = counts(db)
    with caplog.at_level(logging.WARNING, logger="app.ingest"):
        assert rejected(api, ingest(spare, ward.gateway, "alert", alert_payload())) == "the wearable is not issued to a patient"
    assert counts(db) == before
    assert f"ingest rejected device={spare} msg_type=alert reason=the wearable is not issued to a patient" in caplog.text


def test_tc_c21_alerts_outside_the_registry_rules_are_rejected(api, db, ward, system_admin):
    other_gateway = make_device(db, "fixed_gateway", ward.org_id, system_admin.user_id, status="suspended")
    suspended = make_device(db, "wearable", ward.org_id, system_admin.user_id, status="suspended")
    ungranted = make_device(db, "wearable", None, system_admin.user_id)
    ward.issue(ungranted, ward.other_patient_id)  # issued, but its grant is gone
    cases = {
        "unknown device": ingest(uuid.uuid4(), ward.gateway, "alert", alert_payload()),
        "the device is a fixed_gateway, not a wearable": ingest(other_gateway, ward.gateway, "alert", alert_payload()),
        "the wearable is suspended": ingest(suspended, ward.gateway, "alert", alert_payload()),
        "the wearable is not issued to a patient": ingest(ungranted, ward.gateway, "alert", alert_payload()),
        "the attesting gateway is not an active fixed gateway": ingest(ward.wearable, other_gateway, "alert", alert_payload()),
        "no attesting gateway: the mobile path is not ingested yet": ingest(ward.wearable, None, "alert", alert_payload()),
        "the device was not authenticated": ingest(ward.wearable, ward.gateway, "alert", alert_payload(), authenticated=False),
        "a gateway reports only for itself": ingest(other_gateway, ward.gateway, "status", status_payload(),
                                                    device_type="fixed_gateway"),
    }
    before = counts(db)
    assert {reason: rejected(api, body) for reason, body in cases.items()} == {reason: reason for reason in cases}
    assert counts(db) == before


# --- TC-C22 ------------------------------------------------------------------------------------

def test_tc_c22_a_redelivered_message_is_stored_once(api, db, ward):
    message = ingest(ward.wearable, ward.gateway, "alert", alert_payload())
    first = post(api, message)
    after_first = counts(db)
    assert post(api, message) == {"result": "duplicate", "msg_id": first["msg_id"]}
    assert counts(db) == after_first
    assert after_first["alerts"] == after_first["ecg_chunks"] == 1


def test_message_ids_are_per_device(api, db, ward, system_admin):
    """Another device reusing a msg_id does not make the first device's message a duplicate."""
    payload = alert_payload()
    other = make_device(db, "wearable", ward.org_id, system_admin.user_id)
    ward.issue(other, ward.other_patient_id)
    assert post(api, ingest(other, ward.gateway, "alert", payload))["result"] == "stored"
    assert post(api, ingest(ward.wearable, ward.gateway, "alert", payload))["result"] == "stored"


# --- TC-C23 ------------------------------------------------------------------------------------

MALFORMED = {
    "samples do not match n_samples": lambda w, g: ingest(w, g, "alert", alert_payload(n_samples=10, samples=encode([1]))),
    "unknown payload field": lambda w, g: ingest(w, g, "alert", {**alert_payload(), "patient": "P-1"}),
    "wrong payload version": lambda w, g: ingest(w, g, "alert", alert_payload(v=2)),
    "message type the device does not send": lambda w, g: ingest(w, g, "ids_event", ids_payload()),
    "unknown msg_type": lambda w, g: ingest(w, g, "telemetry", {}),
    "envelope field missing": lambda w, g: {k: v for k, v in ingest(w, g, "alert", alert_payload()).items() if k != "hops"},
    "segment_start in the future": lambda w, g: ingest(w, g, "alert", alert_payload(
        segment_start=(datetime.now(UTC) + timedelta(hours=1)).isoformat())),
}


@pytest.mark.parametrize("case", MALFORMED, ids=list(MALFORMED))
def test_tc_c23_a_malformed_message_is_rejected(api, db, ward, case, caplog):
    before = counts(db)
    with caplog.at_level(logging.WARNING, logger="app.ingest"):
        reason = rejected(api, MALFORMED[case](ward.wearable, ward.gateway))
    assert reason and counts(db) == before
    assert f"ingest rejected device={ward.wearable}" in caplog.text


# --- TC-C24 ------------------------------------------------------------------------------------

def test_tc_c24_an_ids_event_is_stored_as_the_attesting_gateways(api, db, ward):
    payload = ids_payload(device_id=str(ward.wearable))
    message = ingest(ward.gateway, ward.gateway, "ids_event", payload, device_type="fixed_gateway")
    assert post(api, message)["result"] == "stored"
    assert post(api, message)["result"] == "duplicate"
    event = db.execute(text("SELECT * FROM security_events")).mappings().one()
    assert (str(event["event_id"]), event["gateway_id"], event["device_id"]) == (payload["msg_id"], ward.gateway, ward.wearable)
    assert (event["mode"], event["predicted_class"], event["outcome"], event["action"], event["action_result"]) == (
        "ips", "dos_flood", "blocked", "drop_source", "applied")
    assert event["ts"] == datetime.fromisoformat(payload["ts"])
    unknown = ingest(ward.gateway, ward.gateway, "ids_event", ids_payload(device_id=str(uuid.uuid4())),
                     device_type="fixed_gateway")
    assert rejected(api, unknown) == "the event names an unknown device"


# --- TC-C25 ------------------------------------------------------------------------------------

def test_tc_c25_reassigning_a_wearable_ends_the_session_and_later_data_goes_to_the_new_patient(api, make_client, db, ward):
    first = post(api, ingest(ward.wearable, ward.gateway, "alert", alert_payload()))
    admin = make_client(ward.admin)
    assert admin.delete(f"/patients/{ward.patient_id}/wearable").status_code == 200
    ended = db.scalar(text("SELECT ended_at FROM monitoring_sessions WHERE session_id = :s"), {"s": first["session_id"]})
    assert ended is not None
    assert rejected(api, ingest(ward.wearable, ward.gateway, "alert", alert_payload())) == (
        "the wearable is not issued to a patient")  # returned: nobody's data

    assert admin.post(f"/patients/{ward.other_patient_id}/wearable", json={"device_id": str(ward.wearable)}).status_code == 201
    second = post(api, ingest(ward.wearable, ward.gateway, "alert", alert_payload()))
    assert second["session_id"] != first["session_id"]
    owners = dict(db.execute(text("SELECT session_id::text, patient_id FROM monitoring_sessions")).all())
    assert owners == {first["session_id"]: ward.patient_id, second["session_id"]: ward.other_patient_id}
    by_patient = dict(db.execute(text("SELECT segment_id::text, patient_id FROM ecg_segments")).all())
    assert by_patient == {first["segment_id"]: ward.patient_id, second["segment_id"]: ward.other_patient_id}


def test_a_session_left_open_for_another_patient_is_ended_by_ingestion(api, db, ward):
    """A session must never collect another patient's data, even if an assignment change missed it."""
    stale = insert(db, """INSERT INTO monitoring_sessions (device_id, patient_id, org_id, path)
                          VALUES (:d, :p, :o, 'fixed') RETURNING session_id""",
                   d=ward.wearable, p=ward.other_patient_id, o=ward.org_id)
    stored = post(api, ingest(ward.wearable, ward.gateway, "alert", alert_payload()))
    assert stored["session_id"] != str(stale)
    assert db.scalar(text("SELECT ended_at FROM monitoring_sessions WHERE session_id = :s"), {"s": stale}) is not None


# --- TC-C26 ------------------------------------------------------------------------------------

def test_tc_c26_a_gateway_going_offline_shows_its_wearables_as_unknown_not_offline(api, db, ward):
    t0 = datetime.now(UTC) - timedelta(minutes=1)
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("online"), received_at=t0))
    assert (ward.device(ward.wearable)["current_mode"], ward.device(ward.wearable)["current_gateway_id"]) == (
        "fixed", ward.gateway)

    offline = ingest(ward.gateway, ward.gateway, "status", status_payload("offline"), device_type="fixed_gateway",
                     received_at=t0 + timedelta(seconds=10))
    assert post(api, offline)["wearables_unknown"] == 1
    wearable = ward.device(ward.wearable)
    # Unknown, still via that gateway, and last heard from when it was last heard from.
    assert (wearable["current_mode"], wearable["current_gateway_id"], wearable["last_seen"]) == ("unknown", ward.gateway, t0)

    # The gateway is back and forwards the wearable's presence again.
    for message in (ingest(ward.gateway, ward.gateway, "status", status_payload("online"), device_type="fixed_gateway",
                           received_at=t0 + timedelta(seconds=20)),
                    ingest(ward.wearable, ward.gateway, "status", status_payload("online"),
                           received_at=t0 + timedelta(seconds=21))):
        post(api, message)
    assert ward.device(ward.wearable)["current_mode"] == "fixed"

    # A disconnect older than what the cloud has heard since is stale: the wearables stay as they are.
    assert post(api, ingest(ward.gateway, ward.gateway, "status", status_payload("offline"), device_type="fixed_gateway",
                            received_at=t0 + timedelta(seconds=15)))["wearables_unknown"] == 0
    assert ward.device(ward.wearable)["current_mode"] == "fixed"
    assert ward.device(ward.gateway)["last_seen"] == t0 + timedelta(seconds=21)


def test_a_wearable_reported_offline_is_unknown_and_detached_from_its_gateway(api, ward):
    t0 = datetime.now(UTC) - timedelta(minutes=1)
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("online"), received_at=t0))
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("offline", reason="mode_switch"),
                     received_at=t0 + timedelta(seconds=5)))
    wearable = ward.device(ward.wearable)
    assert (wearable["current_mode"], wearable["current_gateway_id"], wearable["last_seen"]) == ("unknown", None, t0)


def test_a_suspended_gateways_disconnect_still_turns_its_wearables_unknown(api, db, ward):
    post(api, ingest(ward.wearable, ward.gateway, "status", status_payload("online")))
    db.execute(text("UPDATE devices SET status = 'suspended' WHERE device_id = :g"), {"g": ward.gateway})
    assert rejected(api, ingest(ward.wearable, ward.gateway, "status", status_payload("online"))) == (
        "the attesting gateway is not an active fixed gateway")
    offline = ingest(ward.gateway, ward.gateway, "status", status_payload("offline"), device_type="fixed_gateway")
    assert post(api, offline)["wearables_unknown"] == 1
