"""TC-B01 to TC-B04: mmca-issued certificates against Mosquitto with the fixed-path ACL design.

The broker runs in an eclipse-mosquitto:2 container configured as in
docs/decisions/mqtt_fixed_path_topics.md: a mutual-TLS wearable listener (8883) with
use_identity_as_username, and a loopback services listener (1883) with a password, each with its
own ACL file. This is a stand-in for the Raspberry Pi gateway, not the Pi itself.

Set MM_EVIDENCE_DIR to keep the broker log and the per-case client output.
"""
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from mmca.core.ca import init_ca, issue_device
from mmca.core.config import ensure_layout, load_settings

IMAGE = "docker.io/library/eclipse-mosquitto:2"
ROLE_NAME = "gateway.medmusketeer.local"
PASSPHRASE = "local-test-ca-passphrase"
SERVICES_PASSWORD = "services-test-password"
WAIT = 5


def _image_available():
    if shutil.which("podman") is None:
        return False
    return subprocess.run(["podman", "image", "exists", IMAGE]).returncode == 0


pytestmark = [pytest.mark.interop,
              pytest.mark.skipif(not _image_available(), reason=f"podman with {IMAGE} not available")]

MOSQUITTO_CONF = """\
per_listener_settings true
log_dest stdout
log_type all
connection_messages true

listener 8883
cafile /mosquitto/config/certs/ca.crt
certfile /mosquitto/config/certs/gateway.crt
keyfile /mosquitto/config/certs/gateway.key
require_certificate true
use_identity_as_username true
allow_anonymous false
acl_file /mosquitto/config/wearables.acl

listener 1883 127.0.0.1
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/services.acl
"""

WEARABLES_ACL = """\
pattern write mm/fixed/%u/telemetry
pattern write mm/fixed/%u/alert
pattern write mm/fixed/%u/status
pattern write mm/fixed/%u/command_ack
pattern read  mm/fixed/%u/command
"""

SERVICES_ACL = """\
user {user}
topic read  mm/fixed/+/telemetry
topic read  mm/fixed/+/alert
topic read  mm/fixed/+/status
topic read  mm/fixed/+/command_ack
topic write mm/fixed/+/command
topic write mm/fixed/+/result
"""


class Broker:
    def __init__(self, workdir: Path, evidence: Path | None):
        self.workdir = workdir
        self.evidence = evidence
        self.name = f"mm-broker-test-{uuid.uuid4().hex[:8]}"
        self.records = []
        settings = load_settings(workdir / "ca-root")
        ensure_layout(settings)
        init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
        foreign = load_settings(workdir / "foreign-ca")
        ensure_layout(foreign)
        init_ca(foreign, "MedMusketeer CA", 3650, PASSPHRASE)
        # The services username is a UUIDv4 so that a wearable certificate can carry the same
        # CN (mmca only issues UUIDv4 CNs); TC-B04 uses that colliding wearable.
        self.services_user = str(uuid.uuid4())
        config = workdir / "config"
        certs = config / "certs"
        certs.mkdir(parents=True)
        self.ids = {}
        for name, source, profile, device_id in (
                ("gateway", settings, "gateway", None), ("a", settings, "wearable", None),
                ("b", settings, "wearable", None), ("collide", settings, "wearable", self.services_user),
                ("foreign", foreign, "wearable", None)):
            device_id = device_id or str(uuid.uuid4())
            _fp, output = issue_device(source, profile, device_id, "ec_p256", 365, PASSPHRASE,
                                       confirm=lambda _preview: True)
            self.ids[name] = device_id
            shutil.copy(output / "device.crt", certs / f"{name}.crt")
            shutil.copy(output / "device.key", certs / f"{name}.key")
        shutil.copy(settings.ca_dir / "ca.crt", certs / "ca.crt")
        (config / "mosquitto.conf").write_text(MOSQUITTO_CONF)
        (config / "wearables.acl").write_text(WEARABLES_ACL)
        (config / "services.acl").write_text(SERVICES_ACL.format(user=self.services_user))
        for path in config.rglob("*"):
            # Throwaway test material: readable by the container's mosquitto user.
            os.chmod(path, 0o755 if path.is_dir() else 0o644)
        self.config = config

    def start(self):
        subprocess.run(["podman", "run", "--rm", "-v", f"{self.config}:/mosquitto/config:Z",
                        IMAGE, "mosquitto_passwd", "-b", "-c", "/mosquitto/config/passwd",
                        self.services_user, SERVICES_PASSWORD], check=True, capture_output=True)
        os.chmod(self.config / "passwd", 0o644)
        subprocess.run(["podman", "run", "-d", "--name", self.name,
                        "--add-host", f"{ROLE_NAME}:127.0.0.1",
                        "-v", f"{self.config}:/mosquitto/config:Z", IMAGE], check=True,
                       capture_output=True)
        for _ in range(50):
            if "running" in self.log() or "Opening ipv4 listen socket on port 8883" in self.log():
                break
            time.sleep(0.2)
        time.sleep(0.5)

    def stop(self):
        if self.evidence:
            self.evidence.mkdir(parents=True, exist_ok=True)
            (self.evidence / "mosquitto_broker.txt").write_text(self.log())
            (self.evidence / "broker_cases.json").write_text(json.dumps(
                {"image": IMAGE, "image_version": self.version(), "ids": self.ids,
                 "services_user": self.services_user, "records": self.records}, indent=2))
            for name in ("mosquitto.conf", "wearables.acl", "services.acl"):
                shutil.copy(self.config / name, self.evidence / name)
        subprocess.run(["podman", "rm", "-f", self.name], capture_output=True)

    def log(self):
        result = subprocess.run(["podman", "logs", self.name], capture_output=True, text=True)
        return result.stdout + result.stderr

    def version(self):
        result = subprocess.run(["podman", "exec", self.name, "mosquitto", "-h"],
                                capture_output=True, text=True)
        return (result.stdout or result.stderr).splitlines()[0]

    def _wearable_args(self, cert, host=ROLE_NAME):
        return ["-h", host, "-p", "8883", "-V", "mqttv311", "--cafile", "/mosquitto/config/certs/ca.crt",
                "--cert", f"/mosquitto/config/certs/{cert}.crt",
                "--key", f"/mosquitto/config/certs/{cert}.key"]

    def _services_args(self):
        return ["-h", "127.0.0.1", "-p", "1883", "-V", "mqttv311",
                "-u", self.services_user, "-P", SERVICES_PASSWORD]

    def _exec(self, args, case, label):
        result = subprocess.run(["podman", "exec", self.name, *args], capture_output=True, text=True,
                                timeout=WAIT + 20)
        shown = [arg if arg != SERVICES_PASSWORD else "<redacted>" for arg in args]
        self.records.append({"case": case, "step": label, "command": " ".join(shown),
                             "exit_code": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr})
        return result

    def publish(self, case, label, topic, message, *, cert=None, host=ROLE_NAME, services=False):
        auth = self._services_args() if services else self._wearable_args(cert, host)
        return self._exec(["mosquitto_pub", *auth, "-q", "1", "-t", topic, "-m", message], case, label)

    def subscribe(self, case, label, topic, *, cert=None, services=False, then=None):
        """Subscribe for WAIT seconds; `then` runs while the subscriber is listening."""
        auth = self._services_args() if services else self._wearable_args(cert)
        args = ["mosquitto_sub", *auth, "-q", "1", "-v", "-W", str(WAIT), "-t", topic]
        subscribes = self.log().count("Received SUBSCRIBE")
        process = subprocess.Popen(["podman", "exec", self.name, *args],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # Publish only once the broker has registered the subscription, so that a missing
        # message means a denial and not a race.
        for _ in range(50):
            if self.log().count("Received SUBSCRIBE") > subscribes:
                break
            time.sleep(0.1)
        else:
            process.kill()
            raise AssertionError(f"broker never received the SUBSCRIBE for {topic}")
        if then:
            then()
        stdout, stderr = process.communicate(timeout=WAIT + 20)
        shown = [arg if arg != SERVICES_PASSWORD else "<redacted>" for arg in args]
        self.records.append({"case": case, "step": label, "command": " ".join(shown),
                             "exit_code": process.returncode, "stdout": stdout, "stderr": stderr})
        return stdout, stderr


@pytest.fixture(scope="module")
def broker(tmp_path_factory):
    evidence = os.environ.get("MM_EVIDENCE_DIR")
    instance = Broker(tmp_path_factory.mktemp("broker"), Path(evidence) if evidence else None)
    instance.start()
    yield instance
    instance.stop()


def test_tc_b01_wearable_certificate_completes_mutual_tls(broker):
    a = broker.ids["a"]
    topic = f"mm/fixed/{a}/alert"
    received, _ = broker.subscribe("TC-B01", "monitor alerts", "mm/fixed/+/alert", services=True,
        then=lambda: broker.publish("TC-B01", "publish own alert", topic, '{"type":"test_alert"}', cert="a"))
    assert f'{topic} {{"type":"test_alert"}}' in received
    # use_identity_as_username: the broker logs the certificate CN as the username.
    assert f"u'{a}'" in broker.log()


def test_tc_b01_negative_foreign_ca_and_missing_certificate_are_refused(broker):
    foreign = broker.publish("TC-B01", "foreign-CA client", f"mm/fixed/{broker.ids['foreign']}/alert",
                             "x", cert="foreign")
    assert foreign.returncode != 0
    no_cert = broker._exec(["mosquitto_pub", "-h", ROLE_NAME, "-p", "8883", "-V", "mqttv311",
                            "--cafile", "/mosquitto/config/certs/ca.crt", "-t", "x", "-m", "x"],
                           "TC-B01", "client without certificate")
    assert no_cert.returncode != 0


def test_tc_b01_negative_wearable_rejects_broker_without_role_name(broker):
    # Connecting by IP: the gateway certificate's SANs are its UUID and the role name only.
    result = broker.publish("TC-B01", "hostname check by IP", f"mm/fixed/{broker.ids['a']}/alert",
                            "x", cert="a", host="127.0.0.1")
    assert result.returncode != 0


@pytest.mark.parametrize("msg_type", ["telemetry", "alert", "status", "command_ack"])
def test_tc_b02_wearable_publishes_on_own_topics(broker, msg_type):
    topic = f"mm/fixed/{broker.ids['a']}/{msg_type}"
    received, _ = broker.subscribe("TC-B02", f"monitor {msg_type}", f"mm/fixed/+/{msg_type}",
        services=True, then=lambda: broker.publish("TC-B02", f"publish own {msg_type}", topic,
                                                   "own", cert="a"))
    assert f"{topic} own" in received


def test_tc_b02_wearable_receives_command_on_own_topic(broker):
    topic = f"mm/fixed/{broker.ids['a']}/command"
    received, stderr = broker.subscribe("TC-B02", "subscribe own command", topic, cert="a",
        then=lambda: broker.publish("TC-B02", "services send command", topic, "cmd", services=True))
    assert f"{topic} cmd" in received, stderr


def test_tc_b03_publish_on_another_devices_topic_is_dropped(broker):
    b = broker.ids["b"]
    target = f"mm/fixed/{b}/alert"
    received, _ = broker.subscribe("TC-B03", "monitor alerts", "mm/fixed/+/alert", services=True,
        then=lambda: broker.publish("TC-B03", "A publishes on B's alert", target, "spoofed", cert="a"))
    assert "spoofed" not in received
    assert any("Denied PUBLISH" in line and target in line for line in broker.log().splitlines())


@pytest.mark.parametrize("topic_of", ["b-command", "wildcard-alert"])
def test_tc_b03_subscribe_on_another_devices_topic_is_denied(broker, topic_of):
    b = broker.ids["b"]
    topic = f"mm/fixed/{b}/command" if topic_of == "b-command" else "mm/fixed/+/alert"
    publish_topic = f"mm/fixed/{b}/command" if topic_of == "b-command" else f"mm/fixed/{b}/alert"
    publisher = ({"services": True} if topic_of == "b-command" else {"cert": "b"})
    received, stderr = broker.subscribe("TC-B03", f"A subscribes {topic}", topic, cert="a",
        then=lambda: broker.publish("TC-B03", f"message on {publish_topic}", publish_topic, "private",
                                    **publisher))
    # Mosquitto accepts the SUBSCRIBE and filters by the read ACL at delivery, so the denial
    # shows only as the message not arriving.
    assert "private" not in received, stderr


def test_tc_b04_wearable_with_services_username_gets_no_services_rights(broker):
    a = broker.ids["a"]
    assert broker.ids["collide"] == broker.services_user
    # Reading other devices' alerts is a services right; it must not apply on the wearable listener.
    received, _ = broker.subscribe("TC-B04", "colliding CN subscribes all alerts", "mm/fixed/+/alert",
        cert="collide", then=lambda: broker.publish("TC-B04", "A publishes own alert",
                                                   f"mm/fixed/{a}/alert", "a-alert", cert="a"))
    assert "a-alert" not in received
    # Sending commands is a services right too.
    command = f"mm/fixed/{a}/command"
    received, _ = broker.subscribe("TC-B04", "A listens for commands", command, cert="a",
        then=lambda: broker.publish("TC-B04", "colliding CN sends command", command, "forged",
                                    cert="collide"))
    assert "forged" not in received
    assert any("Denied PUBLISH" in line and command in line for line in broker.log().splitlines())
