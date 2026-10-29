"""The MQTT adapter without a broker: topics to ingest-v1 (D1, D7), and delivery to the API."""
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from app.adapter import Adapter, AdapterSettings, Invalid, Skip, to_ingest
from tests.messages import alert_payload, ids_payload, status_payload

GATEWAY = str(uuid.uuid4())
WEARABLE = str(uuid.uuid4())
RECEIVED_MS = 1_793_000_000_000
NOW = datetime.now(UTC)


def republished(topic: str, payload: dict | str, username: str = GATEWAY) -> dict:
    """What EMQX's mm_ingest rule publishes (D1)."""
    return {"id": "x", "username": username, "clientid": "gw-1", "topic": topic, "qos": 1,
            "payload": payload if isinstance(payload, str) else json.dumps(payload), "publish_received_at": RECEIVED_MS}


def test_an_alert_is_attested_by_the_gateway_in_the_topic():
    payload = alert_payload(n_samples=4)
    body = to_ingest(f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert", republished(f"mm/fixed/{WEARABLE}/alert", payload), NOW)
    assert body["device_id"] == WEARABLE and body["device_type"] == "wearable"
    assert body["attested_by"] == GATEWAY  # from the broker, not from the payload
    assert body["msg_type"] == "alert" and body["payload"] == payload
    assert body["received_at"] == body["hops"]["broker_at"] == datetime.fromtimestamp(RECEIVED_MS / 1000, UTC).isoformat()
    assert body["hops"]["sent_at"] == datetime.fromisoformat(payload["sent_at"]).isoformat()
    assert body["hops"]["adapter_at"] == NOW.isoformat()


def test_gateway_messages_and_broker_events_are_the_gateways_own():
    status = to_ingest(f"ingest/{GATEWAY}/mm/gateway/{GATEWAY}/status",
                       republished(f"mm/gateway/{GATEWAY}/status", status_payload("online")), NOW)
    event = to_ingest(f"ingest/{GATEWAY}/mm/gateway/{GATEWAY}/ids_event",
                      republished(f"mm/gateway/{GATEWAY}/ids_event", ids_payload()), NOW)
    assert (status["device_type"], status["msg_type"]) == ("fixed_gateway", "status")
    assert (event["device_id"], event["msg_type"]) == (GATEWAY, "ids_event")
    for name, state in (("client.connected", "online"), ("client.disconnected", "offline")):
        body = to_ingest(f"ingest/{GATEWAY}/broker/{name}",
                         {"event": name, "username": GATEWAY, "clientid": "gw-1", "timestamp": RECEIVED_MS}, NOW)
        assert (body["device_id"], body["msg_type"], body["payload"]) == (GATEWAY, "status", {"v": 1, "state": state})


@pytest.mark.parametrize("kind", ["telemetry", "result", "command_ack"])
def test_wearable_topics_without_ingestion_are_skipped(kind):
    with pytest.raises(Skip):
        to_ingest(f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/{kind}", republished(f"mm/fixed/{WEARABLE}/{kind}", {}), NOW)


INVALID = {
    "username differs from the topic": (f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert",
                                        republished("t", alert_payload(), username=str(uuid.uuid4()))),
    "gateway reports for another": (f"ingest/{GATEWAY}/mm/gateway/{uuid.uuid4()}/status",
                                    republished("t", status_payload())),
    "wearable id not a UUID": (f"ingest/{GATEWAY}/mm/fixed/not-a-uuid/alert", republished("t", alert_payload())),
    "payload not JSON": (f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert", republished("t", "{not json")),
    "payload not an object": (f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert", republished("t", "[1, 2]")),
    "payload breaks its contract": (f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert",
                                    republished("t", alert_payload(fs_hz=0))),
    "message type not for the device": (f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/ids_event", republished("t", ids_payload())),
}


@pytest.mark.parametrize("case", INVALID, ids=list(INVALID))
def test_tc_c23_messages_failing_their_contract_are_dropped_by_the_adapter(case):
    topic, message = INVALID[case]
    with pytest.raises(Invalid):
        to_ingest(topic, message, NOW)


# --- delivery ----------------------------------------------------------------------------------

def adapter_with(responses: list) -> tuple[Adapter, list]:
    """An Adapter whose API answers with `responses` in turn (an exception is raised instead)."""
    posted = []

    def answer(request: httpx.Request) -> httpx.Response:
        posted.append(json.loads(request.content))
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    settings = AdapterSettings(emqx_adapter_password="p", ingest_secret="s", ingest_url="http://api/internal/ingest")
    return Adapter(settings, httpx.Client(transport=httpx.MockTransport(answer))), posted


def mqtt_message(topic: str, message: dict) -> SimpleNamespace:
    return SimpleNamespace(topic=topic, payload=json.dumps(message).encode(), mid=1, qos=1)


ALERT_TOPIC = f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert"


def test_the_adapter_retries_until_the_api_answers(monkeypatch):
    monkeypatch.setattr("app.adapter.time.sleep", lambda _s: None)
    adapter, posted = adapter_with([httpx.ConnectError("down"), httpx.Response(503),
                                    httpx.Response(200, json={"result": "stored"})])
    message = mqtt_message(ALERT_TOPIC, republished(f"mm/fixed/{WEARABLE}/alert", alert_payload(n_samples=4)))
    assert adapter.handle(message) == "stored"
    assert len(posted) == 3 and posted[0] == posted[2]  # the same message each time


def test_a_rejected_message_is_dropped_not_retried():
    adapter, posted = adapter_with([httpx.Response(422, json={"detail": {"rejected": "unknown device"}})])
    message = mqtt_message(ALERT_TOPIC, republished(f"mm/fixed/{WEARABLE}/alert", alert_payload(n_samples=4)))
    assert adapter.handle(message) == "rejected"
    assert len(posted) == 1


def test_invalid_and_skipped_messages_never_reach_the_api():
    adapter, posted = adapter_with([])
    invalid = mqtt_message(ALERT_TOPIC, republished(f"mm/fixed/{WEARABLE}/alert", alert_payload(v=2)))
    skipped = mqtt_message(f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/telemetry", republished("t", {}))
    assert (adapter.handle(invalid), adapter.handle(skipped)) == ("invalid", "skipped")
    assert adapter.handle(SimpleNamespace(topic=ALERT_TOPIC, payload=b"[]", mid=1, qos=1)) == "invalid"
    assert posted == []
