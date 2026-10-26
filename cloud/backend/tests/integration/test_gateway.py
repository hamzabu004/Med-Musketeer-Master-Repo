"""TC-C14 to TC-C18: gateways against the real EMQX gateway listener, end to end.

The stack runs with a throwaway CA (tests.certs, the real CA tool); devices and credentials are
registered through the API as the system admin, as an operator would. Each test case's results
are kept as evidence in stack/tc_c14_c18_gateway.json; the broker and API logs are kept by the
stack fixture.
"""
import json
import socket
import uuid

import httpx
import pytest

from tests.certs import Issued, TestCA
from tests.integration.stack import (API, PORTS, compose, env_value, evidence, machine_token, register_user,
                                     zitadel_admin)
from tests.mqtt import CLOUD_NAME, Client, tls_context

pytestmark = pytest.mark.integration

GATEWAY_PORT = int(PORTS["EMQX_GATEWAY_PUBLISHED_PORT"])
INTERNAL_PORT = int(PORTS["EMQX_INTERNAL_PUBLISHED_PORT"])
ACCEPTED = {"Success", "No matching subscribers"}  # PUBACK codes for an accepted publish
REFUSED = {"Not authorized", "Bad user name or password"}  # CONNACK codes from the auth hook
RECORD: dict = {}


@pytest.fixture(scope="module")
def admin(stack):
    zitadel, config = zitadel_admin(stack)
    user_id, headers = machine_token(zitadel, config, config["default_org_id"], "tc-c14-admin", "system_admin")
    register_user(stack, user_id, "system_admin")
    with httpx.Client(base_url=API, headers=headers, timeout=15) as client:
        yield client
    evidence("tc_c14_c18_gateway.json", json.dumps(RECORD, indent=2))


def register(admin, issued: Issued, device_type: str) -> str:
    """Register, add the certificate as its credential, activate; returns the credential id."""
    response = admin.post("/admin/devices", json={"device_id": issued.device_id, "type": device_type, "is_testbed": True})
    assert response.status_code in (201, 409), response.text  # 409: a second certificate for the same device
    credential = admin.post(f"/admin/devices/{issued.device_id}/credentials",
                            json={"auth_method": "x509_mtls", "key_type": "ec_p256", "credential_ref": issued.fingerprint})
    assert credential.status_code == 201, credential.text
    if response.status_code == 201:
        assert admin.post(f"/admin/devices/{issued.device_id}/activate").status_code == 200
    return credential.json()["credential_id"]


def gateway(stack_ca: TestCA, issued: Issued | None) -> Client:
    context = tls_context(stack_ca.ca_cert, issued.cert if issued else None, issued.key if issued else None)
    return Client(GATEWAY_PORT, context)


@pytest.fixture
def adapter(stack):
    """A monitor on the internal listener with the adapter's account: it sees what ingestion would."""
    client = Client(INTERNAL_PORT, username="mm-adapter", password=env_value(stack, "EMQX_ADAPTER_PASSWORD"))
    assert client.connect() == "Success"
    assert client.subscribe("ingest/#") == "Granted QoS 1"
    yield client
    client.close()


@pytest.fixture(scope="module")
def active_gateway(admin, stack_ca) -> Issued:
    issued = stack_ca.issue("gateway")
    register(admin, issued, "fixed_gateway")
    return issued


# --- TC-C14 ------------------------------------------------------------------------------------

def test_tc_c14_an_active_gateway_connects_and_its_messages_reach_ingestion(stack_ca, active_gateway, adapter):
    client = gateway(stack_ca, active_gateway)
    assert client.connect() == "Success"
    wearable = str(uuid.uuid4())
    alert = {"v": 1, "msg_id": str(uuid.uuid4()), "seq": 1, "type": "alert", "fs_hz": 360}
    try:
        assert client.subscribe("mm/fixed/+/command") == "Granted QoS 1"
        assert client.publish(f"mm/fixed/{wearable}/alert", json.dumps(alert)) in ACCEPTED
        assert client.publish(f"mm/gateway/{active_gateway.device_id}/status", '{"online": true}') in ACCEPTED
    finally:
        client.close()
    received = {message.topic: json.loads(message.payload) for message in adapter.wait_for(2)}
    prefix = f"ingest/{active_gateway.device_id}"
    assert set(received) == {f"{prefix}/mm/fixed/{wearable}/alert", f"{prefix}/mm/gateway/{active_gateway.device_id}/status"}
    republished = received[f"{prefix}/mm/fixed/{wearable}/alert"]
    assert republished["username"] == active_gateway.device_id  # D1: attested by the broker
    assert republished["topic"] == f"mm/fixed/{wearable}/alert"
    assert json.loads(republished["payload"]) == alert
    assert isinstance(republished["publish_received_at"], int)
    RECORD["tc_c14"] = {"gateway": active_gateway.device_id, "republished": republished}


# --- TC-C15 ------------------------------------------------------------------------------------

def test_tc_c15_a_revoked_credential_is_refused_on_the_next_connect(stack, admin, stack_ca):
    old = stack_ca.issue("gateway")
    credential_id = register(admin, old, "fixed_gateway")
    first = gateway(stack_ca, old)
    assert first.connect() == "Success"
    first.close()

    assert admin.post(f"/admin/credentials/{credential_id}/revoke").status_code == 200
    after_revoke = gateway(stack_ca, old).connect()
    assert after_revoke in REFUSED

    # A new certificate for the same gateway works; the revoked one stays refused.
    new = stack_ca.issue("gateway", old.device_id)
    register(admin, new, "fixed_gateway")
    renewed = gateway(stack_ca, new)
    assert renewed.connect() == "Success"
    renewed.close()
    assert gateway(stack_ca, old).connect() in REFUSED

    # Suspending the device refuses every certificate it has.
    assert admin.post(f"/admin/devices/{old.device_id}/suspend").status_code == 200
    after_suspend = gateway(stack_ca, new).connect()
    assert after_suspend in REFUSED
    RECORD["tc_c15"] = {"after_revoke": after_revoke, "new_certificate": "Success", "after_suspend": after_suspend}
    # The API logs each decision with its reason and check time (a benchmark checkpoint later).
    api_log = compose(stack, "logs", "--no-color", "api").stdout
    decisions = [line for line in api_log.splitlines() if f"emqx authn gateway={old.device_id}" in line]
    assert any("result=deny reason=credential is revoked check_ms=" in line for line in decisions), decisions
    assert any("result=deny reason=device is suspended" in line for line in decisions), decisions


# --- TC-C16 ------------------------------------------------------------------------------------

def test_tc_c16_foreign_missing_and_wearable_certificates_are_refused(admin, stack_ca, tmp_path):
    foreign_ca = TestCA(tmp_path / "foreign")
    foreign = foreign_ca.issue("gateway")
    register(admin, foreign, "fixed_gateway")  # even registered, its chain does not lead to our CA
    wearable = stack_ca.issue("wearable")
    register(admin, wearable, "wearable")
    unregistered = stack_ca.issue("gateway")

    results = {
        "foreign CA": gateway(stack_ca, foreign).connect(),
        "no certificate": gateway(stack_ca, None).connect(),
        "wearable certificate": gateway(stack_ca, wearable).connect(),
        "unregistered gateway": gateway(stack_ca, unregistered).connect(),
    }
    RECORD["tc_c16"] = results
    assert results["foreign CA"] not in REFUSED | {"Success"}, results  # refused in the TLS handshake
    assert results["no certificate"] not in REFUSED | {"Success"}, results
    assert results["wearable certificate"] in REFUSED, results  # by the API: not a gateway
    assert results["unregistered gateway"] in REFUSED, results


# --- TC-C17 ------------------------------------------------------------------------------------

def test_tc_c17_publish_and_subscribe_outside_the_acl_are_denied(stack, stack_ca, active_gateway, adapter):
    client = gateway(stack_ca, active_gateway)
    assert client.connect() == "Success"
    wearable, other_gateway = str(uuid.uuid4()), str(uuid.uuid4())
    denied_publish = [f"mm/fixed/{wearable}/command", f"mm/fixed/{wearable}/other", f"mm/gateway/{other_gateway}/status",
                      f"ingest/{active_gateway.device_id}/mm/fixed/{wearable}/alert", "anything"]
    denied_subscribe = ["mm/fixed/#", "mm/fixed/+/alert", "ingest/#", "#", f"mm/gateway/{other_gateway}/#"]
    try:
        publishes = {topic: client.publish(topic, "x") for topic in denied_publish}
        subscribes = {topic: client.subscribe(topic) for topic in denied_subscribe}
        sentinel = f"mm/fixed/{wearable}/status"
        assert client.publish(sentinel, "sentinel") in ACCEPTED  # sent last; the connection stayed up
    finally:
        client.close()
    RECORD["tc_c17"] = {"publish": publishes, "subscribe": subscribes}
    assert set(publishes.values()) == {"Not authorized"}, publishes
    assert set(subscribes.values()) == {"Not authorized"}, subscribes
    # The monitor sees only the allowed message, nothing that was denied.
    assert [message.topic for message in adapter.wait_for(1)] == [f"ingest/{active_gateway.device_id}/{sentinel}"]
    broker_log = compose(stack, "logs", "--no-color", "emqx").stdout
    assert "not_authorized" in broker_log or "authorization_permission_denied" in broker_log


# --- TC-C18 ------------------------------------------------------------------------------------

def test_tc_c18_the_gateway_verifies_the_cloud_by_its_pinned_name(stack_ca, active_gateway, tmp_path):
    context = tls_context(stack_ca.ca_cert, active_gateway.cert, active_gateway.key)
    with socket.create_connection(("127.0.0.1", GATEWAY_PORT), timeout=10) as raw:
        with context.wrap_socket(raw) as tls:
            presented = tls.getpeercert()
    common_name = dict(field[0] for field in presented["subject"])["commonName"]
    assert common_name == CLOUD_NAME
    assert presented["subjectAltName"] == (("DNS", CLOUD_NAME),)

    wrong_name = Client(GATEWAY_PORT, tls_context(stack_ca.ca_cert, active_gateway.cert, active_gateway.key,
                                                  pinned_name="other.medmusketeer.local")).connect()
    other_ca = Client(GATEWAY_PORT, tls_context(TestCA(tmp_path / "other").ca_cert,
                                                active_gateway.cert, active_gateway.key)).connect()
    RECORD["tc_c18"] = {"presented": {"cn": common_name, "san": presented["subjectAltName"]},
                        "wrong pinned name": wrong_name, "trusting another CA": other_ca}
    assert wrong_name.startswith("SSLCertVerificationError") and "Hostname mismatch" in wrong_name, wrong_name
    assert other_ca.startswith("SSLCertVerificationError"), other_ca
