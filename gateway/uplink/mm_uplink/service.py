"""The uplink service: the gateway's MQTT 5 session with the cloud's EMQX gateway listener.

- TLS: the gateway certificate as client certificate (D4); the cloud must chain to the MedMusketeer
  CA with strict X.509 checks and carry the pinned name, whatever address is dialled.
- At start the stored revocation list is applied to the broker before the cloud is contacted, so
  the gateway enforces it while the cloud is unreachable.
- On every connect it subscribes to the retained list (it arrives at once) and reports its status,
  `revocation_version` included (status-v1). A newer list is stored, applied, then reported.
- A failed broker reload is retried every `retry_s`.

paho-mqtt reconnects on its own. It does not read the reason code of EMQX's 2-byte DISCONNECT
(cloud-backend.md D16), so a disconnect is logged as it reports it, whatever the cause.
"""
import json
import logging
import ssl
import threading
from pathlib import Path

import paho.mqtt.client as mqtt
from cryptography import x509
from paho.mqtt.enums import CallbackAPIVersion

from mm_uplink.config import Config
from mm_uplink.enforce import Enforcer, run_command, sighup_from_pid_file
from mm_uplink.revocations import TOPIC, RevocationStore

log = logging.getLogger(__name__)


# systemd-timesyncd creates this file once the clock has been synchronised since boot.
TIMESYNC_FLAG = Path("/run/systemd/timesync/synchronized")


def clock_synchronised(flag: Path = TIMESYNC_FLAG) -> bool:
    """Whether the clock has been synchronised since boot. Until then it may be fake-hwclock's last
    saved time: buffered data will carry this flag (the backlog, Iteration 4)."""
    return flag.exists()


class PinnedContext(ssl.SSLContext):
    """Checks the server's certificate against `pinned_name`, not against the dialled address."""
    pinned_name = "cloud.medmusketeer.local"

    def wrap_socket(self, sock, *args, server_hostname=None, **kwargs):
        return super().wrap_socket(sock, *args, server_hostname=self.pinned_name, **kwargs)


def tls_context(config: Config) -> PinnedContext:
    context = PinnedContext(ssl.PROTOCOL_TLS_CLIENT)
    context.pinned_name = config.cloud_name
    context.load_verify_locations(cafile=str(config.ca_file))
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    context.load_cert_chain(str(config.cert_file), str(config.key_file))
    return context


def gateway_id(cert_file) -> str:
    """The gateway's device id: its certificate's CN, as EMQX sees it (D1)."""
    cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
    return cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value


class Uplink:
    def __init__(self, config: Config):
        self.config = config
        self.gateway_id = gateway_id(config.cert_file)
        self.store = RevocationStore(config.state_file)
        reload = run_command(config.reload_command) if config.reload_command else sighup_from_pid_file(
            config.mosquitto_pid_file)
        self.enforcer = Enforcer(config.acl_file, reload)
        self._lock = threading.Lock()  # paho's network thread and the retry loop both apply
        self._stop = threading.Event()
        self.mqtt = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=self.gateway_id, protocol=mqtt.MQTTv5)
        self.mqtt.tls_set_context(tls_context(config))
        self.mqtt.reconnect_delay_set(1, 60)
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_message = self._on_message

    # --- lifecycle ---------------------------------------------------------------------------------

    def start(self) -> None:
        if not clock_synchronised():
            log.warning("clock not synchronised since boot (no NTP yet): times may be fake-hwclock's last saved time")
        with self._lock:
            self.enforcer.apply(self.store.current)
        log.info("gateway %s connecting to %s:%s as %s", self.gateway_id, self.config.cloud_host,
                 self.config.cloud_port, self.config.cloud_name)
        self.mqtt.connect_async(self.config.cloud_host, self.config.cloud_port, keepalive=30)
        self.mqtt.loop_start()

    def run_forever(self) -> None:
        self.start()
        while not self._stop.wait(self.config.retry_s):
            self.retry()

    def stop(self) -> None:
        self._stop.set()
        self.mqtt.disconnect()
        self.mqtt.loop_stop()

    def retry(self) -> None:
        with self._lock:
            if not self.enforcer.pending:
                return
            applied = self.enforcer.apply(self.store.current)
        if applied:
            self.publish_status()

    # --- MQTT ----------------------------------------------------------------------------------

    @property
    def status_topic(self) -> str:
        return f"mm/gateway/{self.gateway_id}/status"

    def status(self) -> dict:
        payload = {"v": 1, "state": "online"}
        if self.enforcer.enforced_version is not None:
            payload["revocation_version"] = self.enforcer.enforced_version
        return payload

    def publish_status(self) -> None:
        self.mqtt.publish(self.status_topic, json.dumps(self.status()), qos=1)

    def _on_connect(self, client, _userdata, _flags, code, _props):
        if code.is_failure:
            log.warning("cloud refused the connection: %s", code)
            return
        log.info("connected to the cloud")
        client.subscribe(TOPIC, qos=1)
        self.publish_status()

    def _on_disconnect(self, _client, _userdata, _flags, code, _props):
        if not self._stop.is_set():
            log.warning("disconnected from the cloud (%s); the stored revocation list stays enforced", code)

    def _on_message(self, _client, _userdata, message):
        if message.topic != TOPIC:
            return
        with self._lock:
            listing = self.store.offer(message.payload)
            if listing is None:
                return
            applied = self.enforcer.apply(listing)
        if applied:
            self.publish_status()
