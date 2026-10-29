"""Test helpers for TC-B05 to TC-B08: Mosquitto containers standing in for the gateway's broker and
the cloud, and certificates from the real CA tool (tools/ca-tool).

- The gateway broker is configured as tools/Fixed-Gateway-Setup/setup_mosquitto.sh does (wearable
  mTLS listener, CN as username; services listener with a password), with its wearable ACL in a
  host directory the uplink writes, as /var/lib/medmusketeer on the Pi. It runs as the host user
  (--userns=keep-id), so it reads the uplink's 0600 files as the mosquitto user does on the Pi.
- The cloud stand-in has the cloud certificate (cloud.medmusketeer.local) on a mutual-TLS listener
  for gateways (subscribe to the list, publish their own status), and a password listener inside
  the container from which the tests publish the retained list. The real EMQX path is TC-C29/C30.
- Wearables and monitors are mosquitto clients run inside the gateway container (podman exec).
"""
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CA_TOOL = REPO / "tools" / "ca-tool"
if str(CA_TOOL) not in sys.path:
    sys.path.insert(0, str(CA_TOOL))

from mmca.core.ca import init_ca, issue_cloud, issue_device  # noqa: E402
from mmca.core.config import ensure_layout, load_settings  # noqa: E402

from mm_uplink.enforce import PATTERNS  # noqa: E402

IMAGE = "docker.io/library/eclipse-mosquitto:2.0.21"  # the Pi's version (2026-10-22 hardware evidence)
ROLE_NAME = "gateway.medmusketeer.local"
PASSPHRASE = "uplink-test-ca-passphrase"
SERVICES_USER, SERVICES_PASSWORD = "gw_services", "services-test-password"
CLOUD_USER, CLOUD_PASSWORD = "cloud", "cloud-test-password"
CERTS = "/mosquitto/config/certs"


def podman_available() -> bool:
    return shutil.which("podman") is not None and subprocess.run(
        ["podman", "image", "exists", IMAGE], capture_output=True).returncode == 0


def password_line(user: str, password: str) -> str:
    """A Mosquitto 2 password file line ($7$: PBKDF2-SHA512, 101 iterations), as mosquitto_passwd writes."""
    salt = os.urandom(12)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 101)
    return f"{user}:$7$101${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}\n"


class Material:
    """A throwaway CA with a gateway, three wearables and the cloud server certificate."""

    def __init__(self, root: Path):
        settings = load_settings(root / "ca")
        ensure_layout(settings)
        init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
        self.certs = root / "certs"
        self.certs.mkdir()
        self.ids: dict[str, str] = {}
        for name, profile in (("gateway", "gateway"), ("a", "wearable"), ("b", "wearable"), ("c", "wearable")):
            device_id = str(uuid.uuid4())
            _fp, out = issue_device(settings, profile, device_id, "ec_p256", 365, PASSPHRASE,
                                    confirm=lambda _preview: True)
            shutil.copy(out / "device.crt", self.certs / f"{name}.crt")
            shutil.copy(out / "device.key", self.certs / f"{name}.key")
            self.ids[name] = device_id
        _fp, out = issue_cloud(settings, 365, PASSPHRASE, confirm=lambda _preview: True)
        shutil.copy(out / "server.crt", self.certs / "server.crt")
        shutil.copy(out / "server.key", self.certs / "server.key")
        shutil.copy(settings.ca_dir / "ca.crt", self.certs / "ca.crt")
        for path in self.certs.iterdir():
            path.chmod(0o644)  # throwaway test material, read inside the containers


class Container:
    def __init__(self, workdir: Path, material: Material, label: str):
        self.name = f"mm-uplink-test-{label}-{uuid.uuid4().hex[:6]}"
        self.config = workdir / self.name
        self.config.mkdir()
        shutil.copytree(material.certs, self.config / "certs")
        self.out = workdir / f"{self.name}-clients"
        self.out.mkdir()
        self.processes: list[subprocess.Popen] = []
        self.material = material

    def run_args(self) -> list[str]:
        uid, gid = os.getuid(), os.getgid()
        return ["podman", "run", "-d", "--name", self.name, "--userns=keep-id", "--user", f"{uid}:{gid}",
                "--add-host", f"{ROLE_NAME}:127.0.0.1", "-v", f"{self.config}:/mosquitto/config:Z"]

    def log(self) -> str:
        result = subprocess.run(["podman", "logs", self.name], capture_output=True, text=True)
        return result.stdout + result.stderr

    def wait_log(self, text: str, count: int = 1, timeout: float = 15) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.log().count(text) >= count:
                return True
            time.sleep(0.1)
        return False

    def exec(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["podman", "exec", self.name, *args], capture_output=True, text=True, timeout=30)

    def background(self, label: str, args: list[str], stdin: bool = False) -> subprocess.Popen:
        handle = open(self.out / f"{label}.txt", "w")
        process = subprocess.Popen(["podman", "exec", *(["-i"] if stdin else []), self.name, *args],
                                   stdin=subprocess.PIPE if stdin else None, stdout=handle,
                                   stderr=subprocess.STDOUT, text=True)
        self.processes.append(process)
        return process

    def output(self, label: str) -> str:
        path = self.out / f"{label}.txt"
        return path.read_text() if path.exists() else ""

    def remove(self, evidence: Path | None) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.kill()
        if evidence:
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / f"{self.name.rsplit('-', 1)[0]}.txt").write_text(self.log())
        subprocess.run(["podman", "rm", "-f", self.name], capture_output=True)


class GatewayBroker(Container):
    def __init__(self, workdir: Path, material: Material):
        super().__init__(workdir, material, "gateway")
        self.state = workdir / "state"  # /var/lib/medmusketeer on the Pi
        self.state.mkdir()
        self.acl = self.state / "wearables.acl"
        self.acl.write_text(PATTERNS)  # what setup_mosquitto.sh writes first
        self.acl.chmod(0o600)
        (self.config / "mosquitto.conf").write_text(f"""\
per_listener_settings true
log_dest stdout
log_type all
connection_messages true

listener 8883
cafile {CERTS}/ca.crt
certfile {CERTS}/gateway.crt
keyfile {CERTS}/gateway.key
require_certificate true
use_identity_as_username true
allow_anonymous false
acl_file /mosquitto/state/wearables.acl

listener 1883 127.0.0.1
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/services.acl
""")
        (self.config / "services.acl").write_text(
            f"user {SERVICES_USER}\ntopic read mm/fixed/#\ntopic write mm/fixed/+/command\n")
        (self.config / "passwd").write_text(password_line(SERVICES_USER, SERVICES_PASSWORD))

    def start(self) -> None:
        subprocess.run([*self.run_args(), "-v", f"{self.state}:/mosquitto/state:Z", IMAGE],
                       check=True, capture_output=True)
        assert self.wait_log("listen socket on port 8883"), self.log()

    @property
    def reload_command(self) -> list[str]:
        return ["podman", "kill", "--signal", "HUP", self.name]

    def wearable(self, who: str) -> list[str]:
        return ["-h", ROLE_NAME, "-p", "8883", "-V", "5", "--cafile", f"{CERTS}/ca.crt",
                "--cert", f"{CERTS}/{who}.crt", "--key", f"{CERTS}/{who}.key"]

    def services(self) -> list[str]:
        return ["-h", "127.0.0.1", "-p", "1883", "-V", "5", "-u", SERVICES_USER, "-P", SERVICES_PASSWORD]

    def monitor(self) -> None:
        """Everything wearables manage to publish, as the gateway's services would see it."""
        subscribes = self.log().count("Received SUBSCRIBE")
        self.background("monitor", ["mosquitto_sub", *self.services(), "-q", "1", "-v", "-t", "mm/fixed/#"])
        assert self.wait_log("Received SUBSCRIBE", subscribes + 1), "monitor never subscribed"

    def open_publisher(self, who: str) -> subprocess.Popen:
        """A wearable connection that stays open; each line written to it is published as an alert."""
        device = self.material.ids[who]
        connects = self.log().count(f"u'{device}'")
        process = self.background(f"pub-{who}", ["mosquitto_pub", *self.wearable(who), "-q", "1", "-l",
                                                 "-t", f"mm/fixed/{device}/alert"], stdin=True)
        assert self.wait_log(f"u'{device}'", connects + 1), f"{who} never connected"
        return process

    def open_subscriber(self, who: str) -> subprocess.Popen:
        subscribes = self.log().count("Received SUBSCRIBE")
        process = self.background(f"sub-{who}", ["mosquitto_sub", *self.wearable(who), "-v", "-q", "1",
                                                 "-t", f"mm/fixed/{self.material.ids[who]}/command"])
        assert self.wait_log("Received SUBSCRIBE", subscribes + 1)
        return process

    def command(self, who: str, text: str) -> None:
        self.exec("mosquitto_pub", *self.services(), "-q", "1",
                  "-t", f"mm/fixed/{self.material.ids[who]}/command", "-m", text)

    def fresh_publish(self, who: str, text: str) -> str:
        """A new connection's publish; the PUBACK reason line (mosquitto_pub -d)."""
        result = self.exec("mosquitto_pub", *self.wearable(who), "-d", "-q", "1",
                           "-t", f"mm/fixed/{self.material.ids[who]}/alert", "-m", text)
        return next((line for line in result.stdout.splitlines() if "PUBACK" in line), result.stdout + result.stderr)


class CloudBroker(Container):
    def __init__(self, workdir: Path, material: Material):
        super().__init__(workdir, material, "cloud")
        (self.config / "mosquitto.conf").write_text(f"""\
per_listener_settings true
log_dest stdout
log_type all
connection_messages true

listener 8883
cafile {CERTS}/ca.crt
certfile {CERTS}/server.crt
keyfile {CERTS}/server.key
require_certificate true
use_identity_as_username true
allow_anonymous false
acl_file /mosquitto/config/gateways.acl

listener 1883 127.0.0.1
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/cloud.acl
""")
        # `pattern`, not `topic`: topic lines before any `user` line apply to anonymous clients only.
        (self.config / "gateways.acl").write_text("pattern read mm/revocations/wearables\npattern write mm/gateway/%u/#\n")
        (self.config / "cloud.acl").write_text(f"user {CLOUD_USER}\ntopic readwrite #\n")
        (self.config / "passwd").write_text(password_line(CLOUD_USER, CLOUD_PASSWORD))
        self.port: int | None = None

    def start(self) -> None:
        subprocess.run([*self.run_args(), "-p", "127.0.0.1::8883", IMAGE], check=True, capture_output=True)
        assert self.wait_log("listen socket on port 8883"), self.log()
        port = subprocess.run(["podman", "port", self.name, "8883/tcp"], capture_output=True, text=True, check=True)
        self.port = int(port.stdout.strip().splitlines()[0].rsplit(":", 1)[1])
        self.watch_status()

    def stop(self) -> None:
        subprocess.run(["podman", "stop", "-t", "1", self.name], check=True, capture_output=True)

    def restart(self) -> None:
        """Same container, so the same host port; retained messages are gone (no persistence)."""
        starts = self.log().count("listen socket on port 8883")
        subprocess.run(["podman", "start", self.name], check=True, capture_output=True)
        assert self.wait_log("listen socket on port 8883", starts + 1)
        self.watch_status()

    def cloud(self) -> list[str]:
        return ["-h", "127.0.0.1", "-p", "1883", "-V", "5", "-u", CLOUD_USER, "-P", CLOUD_PASSWORD]

    def watch_status(self) -> None:
        subscribes = self.log().count("Received SUBSCRIBE")
        self.background(f"status-{time.monotonic_ns()}", ["mosquitto_sub", *self.cloud(), "-q", "1", "-v",
                                                          "-t", "mm/gateway/+/status"])
        assert self.wait_log("Received SUBSCRIBE", subscribes + 1)

    def statuses(self) -> str:
        return "".join(path.read_text() for path in sorted(self.out.glob("status-*.txt")))

    def publish_list(self, payload: str) -> None:
        result = self.exec("mosquitto_pub", *self.cloud(), "-q", "1", "-r", "-t", "mm/revocations/wearables",
                           "-m", payload)
        assert result.returncode == 0, result.stderr
