"""TC-C17 (rules part): the D5 topic rules the authorisation hook applies (app.broker)."""
import uuid

import pytest

from app.broker import adapter_may, gateway_may

GATEWAY = str(uuid.uuid4())
WEARABLE = str(uuid.uuid4())


@pytest.mark.parametrize("topic", [f"mm/fixed/{WEARABLE}/{kind}" for kind in
                                   ("alert", "result", "status", "command_ack", "telemetry")]
                         + [f"mm/gateway/{GATEWAY}/ids_event", f"mm/gateway/{GATEWAY}/status",
                            f"mm/gateway/{GATEWAY}/backlog"])
def test_a_gateway_may_publish_these(topic):
    assert gateway_may(GATEWAY, "publish", topic)


@pytest.mark.parametrize("topic", [
    "mm/revocations/wearables",              # only the API publishes the list (REST, D16)
    f"mm/fixed/{WEARABLE}/command",          # commands come from the cloud
    f"mm/fixed/{WEARABLE}/other",
    f"mm/fixed/{WEARABLE}/alert/extra",
    "mm/fixed/not-a-uuid/alert",
    f"mm/fixed/{WEARABLE.upper()}/alert",    # device ids are canonical lower-case UUIDs
    f"mm/gateway/{uuid.uuid4()}/status",     # another gateway's topics
    f"mm/gateway/{GATEWAY}",
    f"mm/gateway/{GATEWAY}/",
    f"ingest/{GATEWAY}/mm/fixed/{WEARABLE}/alert",  # only the broker writes ingest/
    "$SYS/brokers", "anything",
])
def test_a_gateway_may_not_publish_these(topic):
    assert not gateway_may(GATEWAY, "publish", topic)


def test_a_gateway_subscribes_only_to_commands_and_the_revocation_list():
    assert gateway_may(GATEWAY, "subscribe", "mm/fixed/+/command")
    assert gateway_may(GATEWAY, "subscribe", f"mm/fixed/{WEARABLE}/command")
    assert gateway_may(GATEWAY, "subscribe", "mm/revocations/wearables")  # D16
    for topic in ("mm/fixed/#", "mm/fixed/+/alert", "mm/#", "#", "ingest/#", f"mm/gateway/{GATEWAY}/#",
                  "$share/g/mm/fixed/+/command", "mm/fixed/+/+", "mm/revocations/#", "mm/revocations/+",
                  "$share/g/mm/revocations/wearables"):
        assert not gateway_may(GATEWAY, "subscribe", topic), topic


def test_the_adapter_only_reads_ingest():
    assert adapter_may("subscribe", "ingest/#")
    for action, topic in (("publish", "ingest/x"), ("subscribe", "#"), ("subscribe", "mm/fixed/+/alert"),
                          ("publish", f"mm/fixed/{WEARABLE}/command")):
        assert not adapter_may(action, topic)
