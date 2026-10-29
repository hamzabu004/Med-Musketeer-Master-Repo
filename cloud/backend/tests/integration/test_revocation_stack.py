"""TC-C29 and TC-C30: the revocation list and gateway disconnects through the real EMQX (D16).

The API publishes through EMQX's REST API with the key EMQX bootstrapped at start; gateways read
the retained list over their mTLS listener. Results are kept as evidence in
stack/tc_c29_c30_revocation.json. TC-C29's last step recreates the EMQX container, so this module
leaves EMQX freshly started (and healthy) for the modules after it.
"""
import json
import time

import httpx
import pytest

from app.contracts import RevocationList
from app.revocation import TOPIC
from tests.integration.stack import API, compose, evidence, gateway, machine_token, register, register_user, zitadel_admin

pytestmark = pytest.mark.integration

REFUSED = {"Not authorized", "Bad user name or password"}
RECORD: dict = {}


@pytest.fixture(scope="module")
def admin(stack):
    zitadel, config = zitadel_admin(stack)
    user_id, headers = machine_token(zitadel, config, config["default_org_id"], "tc-c29-admin", "system_admin")
    register_user(stack, user_id, "system_admin")
    with httpx.Client(base_url=API, headers=headers, timeout=15) as client:
        yield client
    evidence("tc_c29_c30_revocation.json", json.dumps(RECORD, indent=2, default=str))


def lists(client) -> list[RevocationList]:
    return [RevocationList.model_validate_json(m.payload) for m in client.messages if m.topic == TOPIC]


def subscribed_gateway(stack_ca, admin):
    issued = stack_ca.issue("gateway")
    credential = register(admin, issued, "fixed_gateway")
    client = gateway(stack_ca, issued)
    assert client.connect() == "Success"
    assert client.subscribe(TOPIC) == "Granted QoS 1"
    return issued, credential, client


def published(admin) -> dict:
    response = admin.get("/admin/revocation")
    assert response.status_code == 200, response.text
    return response.json()


# --- TC-C29 ------------------------------------------------------------------------------------

def test_tc_c29_gateways_get_the_retained_list_and_new_versions_and_cannot_publish_it(stack, stack_ca, admin):
    _, _, client = subscribed_gateway(stack_ca, admin)
    try:
        # The API published the list at start; it arrives as soon as the gateway subscribes.
        [first] = client.wait_for(1, where=lambda m: m.topic == TOPIC)
        assert first.retain
        retained = RevocationList.model_validate_json(first.payload)
        assert retained.version == published(admin)["published_version"]

        forged = retained.model_copy(update={"version": retained.version + 100, "devices": []})
        assert client.publish(TOPIC, forged.model_dump_json()) == "Not authorized"

        wearable = stack_ca.issue("wearable")
        register(admin, wearable, "wearable")
        started = time.monotonic()
        assert admin.post(f"/admin/devices/{wearable.device_id}/revoke").status_code == 200
        client.wait_for(2, timeout_s=10, where=lambda m: m.topic == TOPIC)
        elapsed = time.monotonic() - started
        newest = lists(client)[-1]
        assert newest.version > retained.version
        assert wearable.device_id in {str(d.device_id) for d in newest.devices}
        assert elapsed < 10
    finally:
        client.close()
    RECORD["tc_c29"] = {"retained_on_subscribe": retained.version, "forged_publish": "Not authorized",
                        "new_version": newest.version, "revoke_to_gateway_s": round(elapsed, 3)}


def test_tc_c29_the_retained_list_survives_emqx_being_recreated(stack, stack_ca, admin):
    before = published(admin)
    recreated = compose(stack, "up", "--detach", "--wait", "--force-recreate", "--no-deps", "emqx", check=False)
    assert recreated.returncode == 0, recreated.stderr[-2000:]
    _, _, client = subscribed_gateway(stack_ca, admin)
    try:
        [message] = client.wait_for(1, where=lambda m: m.topic == TOPIC)
    finally:
        client.close()
    # Not republished in between (published_at unchanged): the list came from EMQX's disc storage.
    assert published(admin)["published_at"] == before["published_at"]
    assert message.retain
    assert RevocationList.model_validate_json(message.payload).version == before["published_version"]
    RECORD["tc_c29_recreate"] = {"version_after_recreate": before["published_version"],
                                 "published_at_unchanged": before["published_at"]}


# --- TC-C30 ------------------------------------------------------------------------------------

def test_tc_c30_a_revoked_gateway_is_disconnected_at_once_and_refused_after(stack_ca, admin):
    results = {}
    actions = {"credential revoked": "/admin/credentials/{credential}/revoke",
               "device suspended": "/admin/devices/{device}/suspend",
               "device revoked": "/admin/devices/{device}/revoke"}
    for how, path in actions.items():
        issued, credential, client = subscribed_gateway(stack_ca, admin)
        started = time.monotonic()
        response = admin.post(path.format(credential=credential, device=issued.device_id))
        assert response.status_code == 200, response.text
        try:
            assert client.disconnected.wait(5), f"{how}: still connected after 5 s"
            elapsed = time.monotonic() - started
            # EMQX's DISCONNECT, not a dropped socket. Its reason is 0x98 on the wire, but paho 2.1.0
            # does not read the reason from a 2-byte DISCONNECT (tests/mqtt.py), so it is not asserted.
            assert client.disconnect_from_server, f"{how}: {client.disconnect_reason}"
        finally:
            client.close()
        again = gateway(stack_ca, issued)
        reconnect = again.connect()
        again.close()
        assert reconnect in REFUSED, reconnect
        results[how] = {"disconnect_s": round(elapsed, 3), "disconnect_packet_from_server": client.disconnect_from_server,
                        "reconnect": reconnect}
    RECORD["tc_c30"] = results
