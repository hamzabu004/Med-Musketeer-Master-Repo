"""TC-C28 and TC-C31 at the API: the wearable revocation list against the real database (D16).

EMQX's REST API is replaced by a fake that records what the API publishes and whom it disconnects;
the same flow through the real EMQX is in test_revocation_stack. Background tasks run after the
response (so after the commit), and TestClient waits for them, so a request's publish is visible
when the call returns.
"""
import functools
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.auth import Principal
from app.contracts import RevocationList
from app.emqx_api import EmqxError
from app.revocation import TOPIC
from tests.integration.test_ingest import ADAPTER, SECRET
from tests.integration.world import insert, make_device, make_user
from tests.messages import ingest, status_payload

pytestmark = pytest.mark.integration


class FakeEmqx:
    def __init__(self):
        self.published: list[RevocationList] = []
        self.disconnected: list[str] = []
        self.down = False

    async def publish_retained(self, topic: str, payload: str) -> None:
        if self.down:
            raise EmqxError("EMQX is down")
        assert topic == TOPIC
        self.published.append(RevocationList.model_validate_json(payload))

    async def disconnect(self, username: str) -> int:
        if self.down:
            raise EmqxError("EMQX is down")
        self.disconnected.append(username)
        return 1

    @property
    def last(self) -> RevocationList:
        return self.published[-1]


@pytest.fixture
def emqx() -> FakeEmqx:
    return FakeEmqx()


@pytest.fixture
def admin(make_client, system_admin, emqx):
    client = make_client(system_admin, ingest_secret=SECRET)
    client.app.state.revocation.emqx = emqx
    return client


def publish(client, *, force: bool = False):
    """Runs the reconciler's step once, in the app's event loop."""
    return client.portal.call(functools.partial(client.app.state.revocation.publish, force=force))


def register(client, device_type: str, *, expires_at: datetime | None = None) -> tuple[str, str, str]:
    """An active device; (device id, credential id, fingerprint)."""
    device_id = str(uuid.uuid4())
    assert client.post("/admin/devices", json={"device_id": device_id, "type": device_type, "is_testbed": True}).status_code == 201
    fingerprint = uuid.uuid4().hex.upper() * 2
    credential = client.post(f"/admin/devices/{device_id}/credentials", json={
        "auth_method": "x509_mtls", "credential_ref": fingerprint,
        "expires_at": expires_at.isoformat() if expires_at else None})
    assert credential.status_code == 201, credential.text
    assert client.post(f"/admin/devices/{device_id}/activate").status_code == 200
    return device_id, credential.json()["credential_id"], fingerprint


def add_credential(client, device_id: str, *, expires_at: datetime | None = None) -> tuple[str, str]:
    fingerprint = uuid.uuid4().hex.upper() * 2
    credential = client.post(f"/admin/devices/{device_id}/credentials", json={
        "auth_method": "x509_mtls", "credential_ref": fingerprint,
        "expires_at": expires_at.isoformat() if expires_at else None})
    assert credential.status_code == 201, credential.text
    return credential.json()["credential_id"], fingerprint


def state(client) -> dict:
    response = client.get("/admin/revocation")
    assert response.status_code == 200, response.text
    return response.json()


# --- TC-C28 ------------------------------------------------------------------------------------

def test_tc_c28_the_list_follows_every_wearable_transition(admin, emqx):
    wearable, credential, fingerprint = register(admin, "wearable")
    assert state(admin)["version"] == 1  # registering and activating does not change the list
    assert emqx.published == []

    assert admin.post(f"/admin/devices/{wearable}/suspend").status_code == 200
    assert emqx.last.version == 2
    assert [(str(d.device_id), d.status) for d in emqx.last.devices] == [(wearable, "suspended")]
    assert emqx.last.certificates == []

    assert admin.post(f"/admin/devices/{wearable}/activate").status_code == 200
    assert (emqx.last.version, emqx.last.devices) == (3, [])

    # One certificate revoked while the wearable stays active: listed by fingerprint.
    assert admin.post(f"/admin/credentials/{credential}/revoke").status_code == 200
    assert emqx.last.version == 4
    assert [(str(c.device_id), c.fingerprint) for c in emqx.last.certificates] == [(wearable, fingerprint)]
    assert admin.post(f"/admin/credentials/{credential}/revoke").status_code == 200  # again: no new version
    assert len(emqx.published) == 3

    # Revoking the wearable lists the device; its certificates are then covered by that.
    assert admin.post(f"/admin/devices/{wearable}/revoke").status_code == 200
    assert emqx.last.version == 5
    assert [(str(d.device_id), d.status) for d in emqx.last.devices] == [(wearable, "revoked")]
    assert emqx.last.certificates == []
    assert emqx.last.devices[0].since <= datetime.now(UTC)
    assert state(admin) | {"published_at": None} == {
        "version": 5, "published_version": 5, "published_at": None}


def test_tc_c28_expired_certificates_drop_off_the_list(admin, emqx):
    wearable, _, _ = register(admin, "wearable")
    soon = datetime.now(UTC) + timedelta(days=1)
    valid, valid_fingerprint = add_credential(admin, wearable, expires_at=soon)
    expired, _ = add_credential(admin, wearable, expires_at=datetime.now(UTC) - timedelta(days=1))
    assert admin.post(f"/admin/credentials/{valid}/revoke").status_code == 200
    assert admin.post(f"/admin/credentials/{expired}/revoke").status_code == 200
    assert [(c.fingerprint, c.not_after) for c in emqx.last.certificates] == [(valid_fingerprint, soon)]


def test_tc_c28_gateways_are_disconnected_not_listed(admin, emqx):
    gateway, credential, _ = register(admin, "fixed_gateway")
    assert admin.post(f"/admin/devices/{gateway}/suspend").status_code == 200
    assert admin.post(f"/admin/devices/{gateway}/activate").status_code == 200
    assert admin.post(f"/admin/credentials/{credential}/revoke").status_code == 200
    assert admin.post(f"/admin/devices/{gateway}/revoke").status_code == 200
    assert emqx.disconnected == [gateway, gateway, gateway]  # suspend, credential revoke, device revoke
    assert emqx.published == []
    assert state(admin)["version"] == 1


def test_tc_c28_a_change_commits_even_when_emqx_is_down_and_is_published_later(admin, emqx, db):
    wearable, _, _ = register(admin, "wearable")
    emqx.down = True
    assert admin.post(f"/admin/devices/{wearable}/suspend").status_code == 200
    assert db.scalar(text("SELECT status FROM devices WHERE device_id = :d"), {"d": wearable}) == "suspended"
    assert state(admin) | {"published_at": None} == {
        "version": 2, "published_version": 0, "published_at": None}

    emqx.down = False
    assert publish(admin) == 2  # the reconciler's next step
    assert publish(admin) is None  # nothing new
    assert publish(admin, force=True) == 2  # the periodic full republish, same version
    assert [listing.version for listing in emqx.published] == [2, 2]
    assert state(admin)["published_version"] == 2


def test_tc_c28_the_published_list_is_revocation_list_v1(admin, emqx):
    wearable, _, _ = register(admin, "wearable")
    assert admin.post(f"/admin/devices/{wearable}/revoke").status_code == 200
    from app.contracts import schemas
    schema = schemas()["revocation-list-v1"]
    payload = json.loads(emqx.last.model_dump_json())
    assert set(payload) == set(schema["properties"]) and set(schema["required"]) <= set(payload)


def test_tc_c28_a_lowercase_fingerprint_in_the_database_does_not_block_publishing(admin, emqx, db, system_admin):
    """make_device stores lower-case refs, as a row written outside the API might."""
    wearable = make_device(db, "wearable", None, system_admin.user_id)
    credential = db.scalar(text("SELECT credential_id FROM device_credentials WHERE device_id = :d"), {"d": wearable})
    assert admin.post(f"/admin/credentials/{credential}/revoke").status_code == 200
    [listed] = emqx.last.certificates
    assert listed.fingerprint == listed.fingerprint.upper()


# --- TC-C31 ------------------------------------------------------------------------------------

def gateway_status(admin, gateway, version, received_at=None):
    message = ingest(gateway, gateway, "status", status_payload("online", revocation_version=version),
                     device_type="fixed_gateway", received_at=received_at)
    return admin.post("/internal/ingest", json=message, headers=ADAPTER)


@pytest.fixture
def org_admin(make_client, db, system_admin):
    """The admin of an organisation the test grants its gateways to (D17: the gateway view is theirs)."""
    org_id = insert(db, """INSERT INTO organisations (name, kind, zitadel_org_id, registered_by)
                           VALUES ('Ward', 'public', :z, :by) RETURNING org_id""",
                    z=f"z-ward-{uuid.uuid4().hex[:6]}", by=system_admin.user_id)
    client = make_client(Principal(make_user(db, "org_admin", org_id), "org_admin", org_id))
    client.org_id = str(org_id)
    return client


def list_state(org_admin, gateway) -> dict:
    response = org_admin.get(f"/gateways/{gateway}")
    assert response.status_code == 200, response.text
    return response.json()["revocation"]


def behind(org_admin) -> set[str]:
    return {g["device_id"] for g in org_admin.get("/gateways").json() if not g["revocation"]["current"]}


def test_tc_c31_gateways_report_the_version_they_enforce_and_the_org_admin_sees_stale_ones(admin, org_admin, emqx):
    first, _, _ = register(admin, "fixed_gateway")
    second, _, _ = register(admin, "fixed_gateway")
    for gateway in (first, second):
        assert admin.post(f"/admin/devices/{gateway}/grants", json={"org_id": org_admin.org_id}).status_code == 201
    assert list_state(org_admin, first) == {"reported_version": None, "published_version": 0, "current": True}
    assert behind(org_admin) == set()  # nothing published yet
    assert publish(admin, force=True) == 1
    assert behind(org_admin) == {first, second}  # neither has reported

    assert gateway_status(admin, first, 1).status_code == 200
    assert behind(org_admin) == {second}
    assert list_state(org_admin, first) == {"reported_version": 1, "published_version": 1, "current": True}

    wearable, _, _ = register(admin, "wearable")
    assert admin.post(f"/admin/devices/{wearable}/suspend").status_code == 200  # version 2 published
    assert behind(org_admin) == {first, second}
    assert gateway_status(admin, first, 2).status_code == 200
    assert gateway_status(admin, first, 1, received_at=datetime.now(UTC) - timedelta(minutes=5)).status_code == 200
    assert list_state(org_admin, first)["reported_version"] == 2  # the older report is stale

    assert admin.post(f"/admin/devices/{second}/suspend").status_code == 200
    assert behind(org_admin) == set()  # only active gateways count


def test_tc_c31_the_system_admin_does_not_see_which_gateways_enforce_the_list(admin, emqx):
    gateway, _, _ = register(admin, "fixed_gateway")
    assert publish(admin, force=True) == 1
    assert gateway_status(admin, gateway, 1).status_code == 200
    assert set(state(admin)) == {"version", "published_version", "published_at"}
    assert "revocation_version" not in admin.get(f"/admin/devices/{gateway}").json()


def test_tc_c31_a_wearable_status_cannot_carry_a_revocation_version(admin, emqx):
    gateway, _, _ = register(admin, "fixed_gateway")
    wearable, _, _ = register(admin, "wearable")
    message = ingest(wearable, gateway, "status", status_payload("online", revocation_version=3))
    response = admin.post("/internal/ingest", json=message, headers=ADAPTER)
    assert response.status_code == 422
    assert "revocation_version" in response.json()["detail"]["rejected"]
