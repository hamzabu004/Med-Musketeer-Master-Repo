"""MQTT adapter (D1, D7, D15): turns what EMQX republishes on ingest/# into ingest-v1 messages for
the ingestion API. Run as `python -m app.adapter` (the compose service `adapter`).

EMQX republishes every gateway message to ingest/{gateway}/{original topic}, as JSON with the
original payload and the broker's receive time, and each gateway's connect and disconnect to
ingest/{gateway}/broker/{event}. The gateway id in the topic comes from the broker (the certificate
CN), so it is the message's `attested_by`; the payload never says who sent it.

  ingest/{gw}/mm/fixed/{wearable}/alert|status    -> the wearable's alert-payload-v1 or status-v1
  ingest/{gw}/mm/gateway/{gw}/status|ids_event    -> the gateway's status-v1 or ids-event-v1
  ingest/{gw}/broker/client.connected|disconnected -> the gateway's status-v1, online or offline

The adapter validates each payload against its contract before posting it; the API validates
again, as ingest-v1 is all it accepts. Topics with no ingestion yet (telemetry, result,
command_ack, backlog) are logged and skipped.

Delivery is at least once, end to end: the adapter keeps a persistent session (clean start off),
so EMQX holds QoS 1 messages while it is away, and acknowledges a message only once the API has
answered for it, stored, duplicate or rejected. While the API is unreachable it retries the same
message, so order is kept. A rejected message is logged with the API's reason and dropped.
"""
import json
import logging
import queue
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.broker import ADAPTER_USERNAME, GATEWAY_LISTENER
from app.contracts import MESSAGES, describe

log = logging.getLogger(__name__)

TOPIC_FILTER = "ingest/#"
NOT_INGESTED = {"telemetry", "result", "command_ack", "backlog"}  # allowed by D5, no ingestion yet
BROKER_EVENTS = {"client.connected": "online", "client.disconnected": "offline"}
SESSION_EXPIRY_S = 24 * 3600


class AdapterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_", extra="ignore")

    emqx_host: str = "emqx"
    emqx_port: int = 1883
    emqx_adapter_password: SecretStr
    ingest_url: str = "http://api:8000/internal/ingest"
    ingest_secret: SecretStr
    # Exists while the adapter is subscribed; the compose health check looks for it.
    ready_file: Path = Path("/tmp/mm-adapter-ready")
    log_level: str = "INFO"


class Skip(Exception):
    """Not for ingestion (yet); acknowledged and logged."""


class Invalid(Exception):
    """Fails its contract or names the wrong device; acknowledged, logged and dropped."""


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def device_id(level: str) -> str:
    try:
        if str(uuid.UUID(level)) == level:
            return level
    except ValueError:
        pass
    raise Invalid(f"{level!r} is not a device id")


def to_ingest(topic: str, republished: dict, adapter_at: datetime) -> dict:
    """The ingest-v1 message for one message EMQX republished on `topic`; raises Skip or Invalid."""
    levels = topic.split("/")
    if len(levels) < 3 or levels[0] != "ingest":
        raise Invalid(f"unexpected topic {topic}")
    gateway = device_id(levels[1])
    if republished.get("username") != gateway:
        raise Invalid("the republished username differs from the topic")
    rest = levels[2:]
    if rest[0] == "broker" and len(rest) == 2:
        if rest[1] not in BROKER_EVENTS:
            raise Skip(f"broker event {rest[1]}")
        device, device_type, msg_type = gateway, "fixed_gateway", "status"
        payload = {"v": 1, "state": BROKER_EVENTS[rest[1]]}
        broker_ms = republished.get("timestamp")
    elif len(rest) == 4 and rest[:2] == ["mm", "fixed"]:
        device, device_type, msg_type = device_id(rest[2]), "wearable", rest[3]
        payload, broker_ms = original_payload(republished), republished.get("publish_received_at")
    elif len(rest) == 4 and rest[:2] == ["mm", "gateway"]:
        if rest[2] != gateway:
            raise Invalid("a gateway reports only for itself")
        device, device_type, msg_type = gateway, "fixed_gateway", rest[3]
        payload, broker_ms = original_payload(republished), republished.get("publish_received_at")
    else:
        raise Skip(f"topic {'/'.join(rest)}")
    if msg_type in NOT_INGESTED:
        raise Skip(f"{msg_type} is not ingested yet")
    contract = MESSAGES[device_type].get(msg_type)
    if contract is None:
        raise Invalid(f"a {device_type} does not send {msg_type}")
    try:
        parsed = contract.model_validate(payload)
    except ValidationError as error:
        raise Invalid(f"payload: {describe(error)}") from None
    if not isinstance(broker_ms, int):
        raise Invalid("no broker receive time")
    sent_at = getattr(parsed, "sent_at", None)
    return {
        "device_id": device,
        "device_type": device_type,
        "auth_method": "x509_mtls",
        "attested_by": gateway,
        "authenticated": True,
        "auth_metadata": {"listener": GATEWAY_LISTENER, "clientid": republished.get("clientid")},
        "msg_type": msg_type,
        "received_at": iso(broker_ms),
        "hops": {"sent_at": sent_at.isoformat() if sent_at else None, "broker_at": iso(broker_ms),
                 "adapter_at": adapter_at.isoformat()},
        "payload": payload,
    }


def original_payload(republished: dict) -> dict:
    try:
        payload = json.loads(republished.get("payload") or "")
    except (TypeError, ValueError):
        raise Invalid("the payload is not JSON") from None
    if not isinstance(payload, dict):
        raise Invalid("the payload is not a JSON object")
    return payload


class Adapter:
    def __init__(self, settings: AdapterSettings, http: httpx.Client | None = None):
        self.settings = settings
        self.http = http or httpx.Client(timeout=10, headers={
            "Authorization": f"Bearer {settings.ingest_secret.get_secret_value()}"})
        self.inbox: queue.Queue[mqtt.MQTTMessage] = queue.Queue()
        self.mqtt = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=ADAPTER_USERNAME, protocol=mqtt.MQTTv5,
                                manual_ack=True)
        self.mqtt.username_pw_set(ADAPTER_USERNAME, settings.emqx_adapter_password.get_secret_value())
        self.mqtt.reconnect_delay_set(1, 30)
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_subscribe = self.on_subscribe
        self.mqtt.on_disconnect = self.on_disconnect
        self.mqtt.on_message = lambda _c, _u, message: self.inbox.put(message)

    # --- MQTT side (paho's network thread) ---------------------------------------------------------

    def on_connect(self, client, _userdata, _flags, code, _props):
        if code.is_failure:
            log.error("adapter could not connect to EMQX: %s", code)
            return
        log.info("adapter connected to EMQX")
        client.subscribe(TOPIC_FILTER, qos=1)

    def on_subscribe(self, _client, _userdata, _mid, codes, _props):
        if any(code.is_failure for code in codes):
            log.error("adapter subscription to %s refused: %s", TOPIC_FILTER, codes)
            return
        log.info("adapter subscribed to %s", TOPIC_FILTER)
        self.settings.ready_file.touch()

    def on_disconnect(self, _client, _userdata, _flags, code, _props):
        log.warning("adapter disconnected from EMQX: %s", code)
        self.settings.ready_file.unlink(missing_ok=True)

    # --- delivery (one worker, so messages are posted in the order they arrived) -----------------

    def handle(self, message: mqtt.MQTTMessage) -> str:
        """Posts one message; returns what happened. Retries while the API cannot answer."""
        try:
            republished = json.loads(message.payload)
            if not isinstance(republished, dict):
                raise Invalid("not a republished message")
            body = to_ingest(message.topic, republished, datetime.now(UTC))
        except Skip as skip:
            log.info("adapter skipped %s: %s", message.topic, skip)
            return "skipped"
        except (Invalid, ValueError) as error:
            log.warning("adapter dropped %s: %s", message.topic, error)
            return "invalid"
        delay = 1.0
        while True:
            try:
                response = self.http.post(self.settings.ingest_url, json=body)
            except httpx.HTTPError as error:
                log.warning("adapter cannot reach the ingestion API (%s); retrying in %.0f s", error, delay)
            else:
                if response.status_code == 200:
                    return response.json().get("result", "stored")
                if response.status_code == 422:
                    log.warning("ingestion rejected %s: %s", message.topic, response.json().get("detail"))
                    return "rejected"
                log.warning("ingestion answered %s for %s; retrying in %.0f s", response.status_code, message.topic,
                            delay)
            time.sleep(delay)
            delay = min(delay * 2, 30)

    def work(self) -> None:
        while True:
            message = self.inbox.get()
            try:
                self.handle(message)
            except Exception:  # a bug must not stop ingestion of everything after it
                log.exception("adapter failed on %s; dropping it", message.topic)
            self.mqtt.ack(message.mid, message.qos)

    def run(self) -> None:
        self.settings.ready_file.unlink(missing_ok=True)
        threading.Thread(target=self.work, name="ingest", daemon=True).start()
        properties = Properties(PacketTypes.CONNECT)
        properties.SessionExpiryInterval = SESSION_EXPIRY_S
        self.mqtt.connect_async(self.settings.emqx_host, self.settings.emqx_port, keepalive=30, clean_start=False,
                                properties=properties)
        self.mqtt.loop_forever(retry_first_connection=True)


def main() -> None:
    from app.main import configure_logging

    settings = AdapterSettings()  # raises if a required MM_* variable is missing
    configure_logging(settings.log_level)
    Adapter(settings).run()


if __name__ == "__main__":
    main()
