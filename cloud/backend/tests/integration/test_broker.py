"""TC-C15 to TC-C17 at the API: EMQX's hooks against the real database, with certificates issued
by mmca. The same cases through EMQX itself are in test_gateway (full stack)."""
import uuid

import pytest
from sqlalchemy import text

from tests.certs import TestCA

pytestmark = pytest.mark.integration

SECRET = "hook-secret-for-tests-0123456789"
ADAPTER_PASSWORD = "adapter-password-0123456789"
HOOK = {"Authorization": f"Bearer {SECRET}"}


@pytest.fixture(scope="module")
def ca(tmp_path_factory):
    return TestCA(tmp_path_factory.mktemp("ca"))


@pytest.fixture
def broker(make_client):
    return make_client(None, emqx_hook_secret=SECRET, emqx_adapter_password=ADAPTER_PASSWORD)


def register(db, device_id: str, device_type: str, fingerprint: str, *, status: str = "active",
             credential_status: str = "active", expires: str | None = None) -> None:
    db.execute(text("INSERT INTO devices (device_id, type, status, is_testbed) VALUES (:d, :t, :s, true)"),
               {"d": device_id, "t": device_type, "s": status})
    db.execute(text("""INSERT INTO device_credentials (device_id, auth_method, credential_ref, status, expires_at)
                       VALUES (:d, 'x509_mtls', :fp, :s, CAST(:e AS timestamptz))"""),
               {"d": device_id, "fp": fingerprint, "s": credential_status, "e": expires})


def authn(client, issued, **overrides):
    body = {"username": issued.device_id, "clientid": "c1", "listener": "ssl:gateway",
            "cert_pem": issued.emqx_cert_pem, **overrides}
    response = client.post("/internal/emqx/authn/gateway", json=body, headers=HOOK)
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_tc_c15_an_active_gateway_with_its_registered_certificate_is_allowed(broker, db, ca):
    gateway = ca.issue("gateway")
    register(db, gateway.device_id, "fixed_gateway", gateway.fingerprint)
    assert authn(broker, gateway) == "allow"


@pytest.mark.parametrize("case", [
    "credential revoked", "credential expired", "device suspended", "device revoked",
    "another certificate of the same gateway", "wearable certificate", "unregistered gateway",
])
def test_tc_c15_c16_refused_gateways(broker, db, ca, case):
    gateway = ca.issue("wearable" if case == "wearable certificate" else "gateway")
    kwargs = {"credential revoked": {"credential_status": "revoked"},
              "credential expired": {"expires": "2020-01-01T00:00:00Z"},
              "device suspended": {"status": "suspended"},
              "device revoked": {"status": "revoked"}}.get(case, {})
    if case == "wearable certificate":
        register(db, gateway.device_id, "wearable", gateway.fingerprint)
    elif case == "another certificate of the same gateway":
        register(db, gateway.device_id, "fixed_gateway", gateway.fingerprint)
        gateway = ca.issue("gateway", gateway.device_id)  # a second certificate, not registered
    elif case != "unregistered gateway":
        register(db, gateway.device_id, "fixed_gateway", gateway.fingerprint, **kwargs)
    assert authn(broker, gateway) == "deny"


def test_a_revoked_certificate_is_refused_while_the_gateways_new_one_works(broker, db, ca):
    old = ca.issue("gateway")
    register(db, old.device_id, "fixed_gateway", old.fingerprint, credential_status="revoked")
    new = ca.issue("gateway", old.device_id)
    db.execute(text("INSERT INTO device_credentials (device_id, auth_method, credential_ref) VALUES (:d, 'x509_mtls', :fp)"),
               {"d": new.device_id, "fp": new.fingerprint})
    assert authn(broker, old) == "deny"
    assert authn(broker, new) == "allow"


@pytest.mark.parametrize("overrides", [
    {"listener": "tcp:internal"},
    {"username": str(uuid.uuid4())},     # not the certificate's CN
    {"cert_pem": "not base64!"},
    {"cert_pem": "QUJD"},                # Base64, not a certificate
    {"username": "mm-adapter"},
])
def test_inconsistent_or_malformed_requests_are_refused(broker, db, ca, overrides):
    gateway = ca.issue("gateway")
    register(db, gateway.device_id, "fixed_gateway", gateway.fingerprint)
    assert authn(broker, gateway, **overrides) == "deny"


def test_hooks_answer_only_the_broker(broker, make_client, ca):
    gateway = ca.issue("gateway")
    body = {"username": gateway.device_id, "listener": "ssl:gateway", "cert_pem": gateway.emqx_cert_pem}
    for path in ("/internal/emqx/authn/gateway", "/internal/emqx/authn/service", "/internal/emqx/authz"):
        assert broker.post(path, json=body).status_code == 401
        assert broker.post(path, json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    unconfigured = make_client(None)
    assert unconfigured.post("/internal/emqx/authz", json=body, headers=HOOK).status_code == 503


@pytest.mark.parametrize("username,password,listener,result", [
    ("mm-adapter", ADAPTER_PASSWORD, "tcp:internal", "allow"),
    ("mm-adapter", "wrong", "tcp:internal", "deny"),
    ("mm-adapter", ADAPTER_PASSWORD, "ssl:gateway", "deny"),
    ("someone", ADAPTER_PASSWORD, "tcp:internal", "deny"),
])
def test_the_adapter_logs_in_with_its_password_on_the_internal_listener(broker, username, password, listener, result):
    response = broker.post("/internal/emqx/authn/service", headers=HOOK,
                           json={"username": username, "password": password, "listener": listener})
    assert response.json() == {"result": result}


def test_tc_c17_topic_access_also_needs_an_active_gateway(broker, db, ca):
    gateway = ca.issue("gateway")
    register(db, gateway.device_id, "fixed_gateway", gateway.fingerprint)
    alert = f"mm/fixed/{uuid.uuid4()}/alert"

    def authz(action, topic, username=gateway.device_id, listener="ssl:gateway"):
        return broker.post("/internal/emqx/authz", headers=HOOK, json={
            "username": username, "listener": listener, "action": action, "topic": topic}).json()["result"]

    assert authz("publish", alert) == "allow"
    assert authz("subscribe", "mm/fixed/+/command") == "allow"
    assert authz("publish", alert.replace("alert", "command")) == "deny"
    assert authz("publish", alert, listener="tcp:internal") == "deny"
    assert authz("subscribe", "ingest/#", username="mm-adapter", listener="tcp:internal") == "allow"
    assert authz("subscribe", "ingest/#", username="mm-adapter", listener="ssl:gateway") == "deny"
    db.execute(text("UPDATE devices SET status = 'suspended' WHERE device_id = :d"), {"d": gateway.device_id})
    assert authz("publish", alert) == "deny"
