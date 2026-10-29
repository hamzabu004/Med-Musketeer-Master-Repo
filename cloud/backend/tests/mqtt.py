"""Test helper: a synchronous MQTT 5 client (paho-mqtt 2) that records the broker's reason codes,
for the gateway listener tests. It verifies the server as a gateway does: the MedMusketeer CA
only, strict X.509 checks, and the pinned name cloud.medmusketeer.local, whatever address it
connects to."""
import ssl
import threading
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

CLOUD_NAME = "cloud.medmusketeer.local"
TIMEOUT_S = 10


class PinnedContext(ssl.SSLContext):
    """Checks the server certificate against `pinned_name`, not against the connect address."""
    pinned_name = CLOUD_NAME

    def wrap_socket(self, sock, *args, server_hostname=None, **kwargs):
        return super().wrap_socket(sock, *args, server_hostname=self.pinned_name, **kwargs)


def tls_context(ca_file: Path, cert: Path | None = None, key: Path | None = None,
                pinned_name: str = CLOUD_NAME) -> PinnedContext:
    context = PinnedContext(ssl.PROTOCOL_TLS_CLIENT)
    context.pinned_name = pinned_name
    context.load_verify_locations(cafile=str(ca_file))
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    if cert is not None:
        context.load_cert_chain(str(cert), str(key))
    return context


class Client:
    def __init__(self, port: int, context: ssl.SSLContext | None = None, username: str | None = None,
                 password: str | None = None):
        self.port = port
        self.mqtt = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"test-{uuid.uuid4().hex[:8]}",
                                protocol=mqtt.MQTTv5)
        if context is not None:
            self.mqtt.tls_set_context(context)
        if username is not None:
            self.mqtt.username_pw_set(username, password)
        self.connected = threading.Event()
        self.connack: str | None = None
        self.disconnected = threading.Event()  # set when an established session ends
        self.disconnect_reason: str | None = None
        # Whether the broker ended it with a DISCONNECT packet. paho-mqtt 2.1.0 drops a DISCONNECT's
        # reason code when the packet is 2 bytes (code + empty properties), as EMQX's kick is, and
        # reports "Normal disconnection"; mosquitto_sub shows the same kick as 152 (0x98).
        self.disconnect_from_server = False
        self.acks: dict[int, list[str]] = {}
        self.ack_events: dict[int, threading.Event] = {}
        self.messages: list[mqtt.MQTTMessage] = []
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_publish = lambda _c, _u, mid, code, _p: self._ack(mid, [code])
        self.mqtt.on_subscribe = lambda _c, _u, mid, codes, _p: self._ack(mid, codes)
        self.mqtt.on_message = lambda _c, _u, message: self.messages.append(message)

    def _on_connect(self, _client, _userdata, _flags, code, _props):
        self.connack = str(code)
        self.connected.set()

    def _on_disconnect(self, _client, _userdata, _flags, code, _props):
        if self.connack is None:
            self.connack = f"disconnected: {code}"
        elif not self.disconnected.is_set():
            self.disconnect_reason = str(code)
            self.disconnect_from_server = _flags.is_disconnect_packet_from_server
            self.disconnected.set()
        self.connected.set()

    def _ack(self, mid: int, codes) -> None:
        self.acks[mid] = [str(code) for code in codes]
        self.ack_events.setdefault(mid, threading.Event()).set()

    def connect(self) -> str:
        """The CONNACK reason ("Success", "Not authorized", ...) or the TLS/socket error."""
        try:
            self.mqtt.connect("127.0.0.1", self.port, keepalive=30)
        except (ssl.SSLError, OSError) as error:
            return f"{type(error).__name__}: {error}"
        self.mqtt.loop_start()
        if not self.connected.wait(TIMEOUT_S):
            return "timeout"
        return self.connack

    def _wait(self, mid: int) -> list[str]:
        if not self.ack_events.setdefault(mid, threading.Event()).wait(TIMEOUT_S):
            raise TimeoutError(f"no acknowledgement for message {mid}")
        return self.acks[mid]

    def publish(self, topic: str, payload: bytes | str) -> str:
        """The PUBACK reason (QoS 1)."""
        return self._wait(self.mqtt.publish(topic, payload, qos=1).mid)[0]

    def subscribe(self, topic: str) -> str:
        """The SUBACK reason ("Granted QoS 1", "Not authorized", ...)."""
        return self._wait(self.mqtt.subscribe(topic, qos=1)[1])[0]

    def wait_for(self, count: int, timeout_s: float = TIMEOUT_S, where=lambda message: True) -> list[mqtt.MQTTMessage]:
        """The messages received so far that match `where`, once there are `count` (or on timeout)."""
        deadline = time.monotonic() + timeout_s
        while len(matched := [m for m in self.messages if where(m)]) < count and time.monotonic() < deadline:
            time.sleep(0.05)
        return matched

    def close(self) -> None:
        self.mqtt.disconnect()
        self.mqtt.loop_stop()
