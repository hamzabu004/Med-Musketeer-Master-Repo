"""TC-C20 to TC-C26 end to end: a gateway publishes over the mTLS listener, EMQX republishes to
ingest/#, the adapter posts ingest-v1, and the API stores it (D1, D7, D15).

Devices are registered through the API as the system admin; the organisation, patient and
wearable issue are arranged in the database directly, as the organisation API is tested
elsewhere. Results are kept as evidence in stack/tc_c20_c26_ingestion.json.
"""
import json
import time
import uuid

import httpx
import pytest

from tests.integration.stack import API, compose, evidence, gateway, machine_token, register, register_user, zitadel_admin
from tests.messages import alert_payload, ids_payload, status_payload

pytestmark = pytest.mark.integration

ACCEPTED = {"Success", "No matching subscribers"}
RECORD: dict = {}


def sql(stack, statement: str) -> list[list[str]]:
    """Runs one statement as the database owner; rows of text fields."""
    result = compose(stack, "exec", "-T", "postgres", "psql", "-U", "postgres", "-d", "medmusketeer", "-AtF", "\t",
                     "-v", "ON_ERROR_STOP=1", "-c", statement)
    return [line.split("\t") for line in result.stdout.splitlines() if line]


def scalar(stack, statement: str) -> str | None:
    rows = sql(stack, statement)
    return rows[0][0] if rows else None


def eventually(check, timeout_s: float = 30):
    """Polls until `check()` is truthy; returns its last value."""
    deadline = time.monotonic() + timeout_s
    while not (value := check()) and time.monotonic() < deadline:
        time.sleep(0.3)
    return value


@pytest.fixture(scope="module")
def ward(stack, stack_ca):
    """A gateway and two wearables registered through the API; the first wearable is issued to a
    patient of an organisation it is granted to, the second is granted but not issued."""
    zitadel, config = zitadel_admin(stack)
    user_id, headers = machine_token(zitadel, config, config["default_org_id"], "tc-c20-admin", "system_admin")
    register_user(stack, user_id, "system_admin")
    issued = {name: stack_ca.issue(kind) for name, kind in
              (("gateway", "gateway"), ("wearable", "wearable"), ("spare", "wearable"))}
    with httpx.Client(base_url=API, headers=headers, timeout=15) as admin:
        register(admin, issued["gateway"], "fixed_gateway")
        register(admin, issued["wearable"], "wearable")
        register(admin, issued["spare"], "wearable")
    org = scalar(stack, "INSERT INTO organisations (name, kind) VALUES ('Ingestion Ward', 'public') RETURNING org_id")
    actor = scalar(stack, f"""INSERT INTO users (zitadel_sub, role, org_id)
                              VALUES ('tc-c20-{uuid.uuid4()}', 'org_admin', '{org}') RETURNING user_id""")
    patient = scalar(stack, f"INSERT INTO patients (org_id, pseudonym) VALUES ('{org}', 'P-C20') RETURNING patient_id")
    for device in ("wearable", "spare"):
        sql(stack, f"""INSERT INTO device_grants (device_id, org_id, granted_by)
                       VALUES ('{issued[device].device_id}', '{org}', '{actor}')""")
    sql(stack, f"""INSERT INTO device_assignments (device_id, patient_id, issued_by)
                   VALUES ('{issued["wearable"].device_id}', '{patient}', '{actor}')""")
    yield {"gateway": issued["gateway"], "wearable": issued["wearable"].device_id, "spare": issued["spare"].device_id,
           "patient": patient}
    evidence("tc_c20_c26_ingestion.json", json.dumps(RECORD, indent=2))


def publish(stack_ca, ward, *messages: tuple[str, dict | str]) -> list[str]:
    client = gateway(stack_ca, ward["gateway"])
    assert client.connect() == "Success"
    try:
        return [client.publish(topic, payload if isinstance(payload, str) else json.dumps(payload))
                for topic, payload in messages]
    finally:
        client.close()


def log_when(stack, service: str, ready) -> str:
    """The service's log if `ready(log)`, else an empty string (for eventually)."""
    log = compose(stack, "logs", "--no-color", service).stdout
    return log if ready(log) else ""


def alerts_of(stack, wearable: str) -> int:
    return int(scalar(stack, f"SELECT count(*) FROM alerts WHERE device_id = '{wearable}'"))


def test_tc_c20_c22_an_alert_from_a_gateway_is_stored_once_with_the_brokers_attestation(stack, stack_ca, ward):
    gateway_id, wearable = ward["gateway"].device_id, ward["wearable"]
    payload = alert_payload()
    topic = f"mm/fixed/{wearable}/alert"
    # Published twice, as a QoS 1 redelivery would be.
    assert set(publish(stack_ca, ward, (topic, payload), (topic, payload))) <= ACCEPTED
    assert eventually(lambda: alerts_of(stack, wearable) == 1)
    time.sleep(2)  # give the second copy time to arrive, if it were going to be stored
    row = sql(stack, f"""
        SELECT k.attested_by, k.auth_method, k.n_samples, g.patient_id, s.path, a.origin, m.seq,
               m.broker_at IS NOT NULL AND m.adapter_at >= m.broker_at AND m.ingested_at >= m.adapter_at,
               d.current_gateway_id
        FROM alerts a JOIN classifications c USING (classification_id) JOIN ecg_segments g USING (segment_id)
        JOIN ecg_chunks k USING (segment_id) JOIN monitoring_sessions s USING (session_id)
        JOIN ingested_messages m ON m.device_id = a.device_id JOIN devices d ON d.device_id = a.device_id
        WHERE a.device_id = '{wearable}'""")
    RECORD["tc_c20_c22"] = {"alerts": alerts_of(stack, wearable), "row": row[0]}
    assert alerts_of(stack, wearable) == 1  # TC-C22
    assert row == [[gateway_id, "x509_mtls", "1080", ward["patient"], "fixed", "wearable", "7", "t", gateway_id]]
    api_log = compose(stack, "logs", "--no-color", "api").stdout
    assert f"ingest duplicate device={wearable} msg_type=alert" in api_log


def test_tc_c21_c23_unissued_and_malformed_alerts_are_rejected_and_logged(stack, stack_ca, ward):
    spare, wearable = ward["spare"], ward["wearable"]
    before = alerts_of(stack, wearable)
    results = publish(stack_ca, ward, (f"mm/fixed/{spare}/alert", alert_payload()),
                      (f"mm/fixed/{wearable}/alert", alert_payload(fs_hz=0)),
                      (f"mm/fixed/{wearable}/alert", "not json"))
    assert set(results) <= ACCEPTED  # the broker accepts them; ingestion refuses
    reason = "reason=the wearable is not issued to a patient"
    api_log = eventually(lambda: log_when(stack, "api", lambda log: reason in log))
    adapter_log = eventually(lambda: log_when(stack, "adapter", lambda log: log.count("adapter dropped") >= 2))
    rejected = [line for line in api_log.splitlines() if f"ingest rejected device={spare}" in line]
    dropped = [line for line in adapter_log.splitlines() if "adapter dropped" in line]
    RECORD["tc_c21_c23"] = {"api": rejected, "adapter": dropped}
    assert rejected and reason in rejected[-1]  # TC-C21
    assert any("payload: fs_hz" in line for line in dropped) and any("not JSON" in line for line in dropped)  # TC-C23
    assert alerts_of(stack, spare) == 0 and alerts_of(stack, wearable) == before


def test_tc_c24_an_ids_event_is_stored_as_the_publishing_gateways(stack, stack_ca, ward):
    gateway_id = ward["gateway"].device_id
    payload = ids_payload(device_id=ward["wearable"])
    assert set(publish(stack_ca, ward, (f"mm/gateway/{gateway_id}/ids_event", payload))) <= ACCEPTED
    row = eventually(lambda: sql(stack, f"""SELECT gateway_id, device_id, mode, predicted_class FROM security_events
                                            WHERE event_id = '{payload["msg_id"]}'"""))
    RECORD["tc_c24"] = row
    assert row == [[gateway_id, ward["wearable"], "ips", "dos_flood"]]


def test_tc_c26_when_the_gateway_disconnects_its_wearables_become_unknown(stack, stack_ca, ward):
    gateway_id, wearable = ward["gateway"].device_id, ward["wearable"]
    mode = f"SELECT current_mode FROM devices WHERE device_id = '{wearable}'"
    client = gateway(stack_ca, ward["gateway"])
    assert client.connect() == "Success"
    try:
        assert client.publish(f"mm/fixed/{wearable}/status", json.dumps(status_payload("online"))) in ACCEPTED
        assert eventually(lambda: scalar(stack, mode) == "fixed")
    finally:
        client.close()  # EMQX's disconnect event, through mm_presence and the adapter
    assert eventually(lambda: scalar(stack, mode) == "unknown")
    row = sql(stack, f"SELECT current_mode, current_gateway_id FROM devices WHERE device_id = '{wearable}'")
    RECORD["tc_c26"] = {"after_disconnect": row[0]}
    assert row == [["unknown", gateway_id]]


def test_messages_wait_in_the_broker_while_the_adapter_is_down(stack, stack_ca, ward):
    """At-least-once delivery: the adapter's persistent session keeps QoS 1 messages for it."""
    wearable = ward["wearable"]
    before = alerts_of(stack, wearable)
    compose(stack, "stop", "adapter")
    try:
        assert set(publish(stack_ca, ward, (f"mm/fixed/{wearable}/alert", alert_payload()))) <= ACCEPTED
        time.sleep(1)
        assert alerts_of(stack, wearable) == before
    finally:
        compose(stack, "start", "adapter")
    assert eventually(lambda: alerts_of(stack, wearable) == before + 1)
    RECORD["adapter_restart"] = {"before": before, "after": alerts_of(stack, wearable)}
    # Healthy again before the other stack tests look at the services.
    assert eventually(lambda: '"healthy"' in compose(stack, "ps", "--format", "json", "adapter").stdout, 60)
