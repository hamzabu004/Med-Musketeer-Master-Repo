"""Iteration 4, Slice 0 spike: how can the gateway's Mosquitto enforce the wearable revocation list?

Run with the CA tool's environment (it issues throwaway certificates with mmca):
    tools/ca-tool/.venv/bin/python docs/testing/evidence/2026-10-29/revocation-spike/spike_mosquitto.py

Needs podman and the images below. The broker is configured as in
tools/Fixed-Gateway-Setup/setup_mosquitto.sh: a mutual-TLS wearable listener (8883, the certificate
CN is the username) and a loopback services listener (1883, password). Writes results.json and one
broker log per run next to this file.

Mechanism A, generated ACL file + SIGHUP: the uplink writes `user <id>` / `topic deny #` for each
listed wearable and sends SIGHUP. Checks: an open connection's publishes and deliveries after the
reload, whether it is disconnected, a fresh connection, another wearable, and lifting the deny.

Mechanism B, dynamic security plugin on the wearable listener: checks whether a wearable that the
plugin does not know may connect (does the plugin authenticate certificate identities at all), and
whether `disableClient` (sent with mosquitto_ctrl as the gateway) disconnects and refuses it.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / "tools" / "ca-tool"))
from mmca.core.ca import init_ca, issue_device  # noqa: E402
from mmca.core.config import ensure_layout, load_settings  # noqa: E402

IMAGES = ["docker.io/library/eclipse-mosquitto:2.0.21", "docker.io/library/eclipse-mosquitto:2"]
ROLE_NAME = "gateway.medmusketeer.local"
PASSPHRASE = "spike-ca-passphrase"
SERVICES_USER = "gw_services"
SERVICES_PASSWORD = "spike-services-password"
CERTS = "/mosquitto/config/certs"

COMMON_CONF = f"""\
per_listener_settings true
log_dest stdout
log_type all
connection_messages true

listener 1883 127.0.0.1
allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/services.acl

listener 8883
cafile {CERTS}/ca.crt
certfile {CERTS}/gateway.crt
keyfile {CERTS}/gateway.key
require_certificate true
use_identity_as_username true
"""
ACL_CONF = "allow_anonymous false\nacl_file /mosquitto/config/wearables.acl\n"
DYNSEC_CONF = ("plugin /usr/lib/mosquitto_dynamic_security.so\n"
               "plugin_opt_config_file /mosquitto/config/dynsec.json\n")

WEARABLE_PATTERNS = """\
pattern write mm/fixed/%u/telemetry
pattern write mm/fixed/%u/alert
pattern write mm/fixed/%u/status
pattern write mm/fixed/%u/command_ack
pattern read  mm/fixed/%u/command
"""
SERVICES_ACL = f"""\
user {SERVICES_USER}
topic read  mm/fixed/#
topic write mm/fixed/+/command
"""


def password_line(user: str, password: str) -> str:
    """A Mosquitto 2 password file line ($7$: PBKDF2-SHA512, 101 iterations), as mosquitto_passwd writes."""
    salt = os.urandom(12)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 101)
    return f"{user}:$7$101${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}\n"


def wearables_acl(denied: list[str]) -> str:
    return WEARABLE_PATTERNS + "".join(f"\nuser {d}\ntopic deny #\n" for d in denied)


class Material:
    """CA, gateway certificate and wearable certificates, issued once for every run."""

    def __init__(self, root: Path):
        settings = load_settings(root / "ca")
        ensure_layout(settings)
        init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
        self.certs = root / "certs"
        self.certs.mkdir()
        self.ids = {}
        for name, profile in (("gateway", "gateway"), ("a", "wearable"), ("b", "wearable"), ("c", "wearable")):
            device_id = str(uuid.uuid4())
            _fp, out = issue_device(settings, profile, device_id, "ec_p256", 365, PASSPHRASE,
                                    confirm=lambda _preview: True)
            shutil.copy(out / "device.crt", self.certs / f"{name}.crt")
            shutil.copy(out / "device.key", self.certs / f"{name}.key")
            self.ids[name] = device_id
        shutil.copy(settings.ca_dir / "ca.crt", self.certs / "ca.crt")


class Broker:
    def __init__(self, image: str, material: Material, workdir: Path, conf: str, files: dict[str, str]):
        self.image, self.material = image, material
        self.name = f"mm-spike-{uuid.uuid4().hex[:8]}"
        self.config = workdir / self.name
        shutil.copytree(material.certs, self.config / "certs")
        (self.config / "mosquitto.conf").write_text(COMMON_CONF + conf)
        (self.config / "services.acl").write_text(SERVICES_ACL)
        for name, content in files.items():
            (self.config / name).write_text(content)
        self.out = workdir / f"{self.name}-clients"
        self.out.mkdir()
        self.processes = []

    def start(self):
        (self.config / "passwd").write_text(password_line(SERVICES_USER, SERVICES_PASSWORD))
        # Throwaway material; the dynamic security plugin also rewrites its file, so the
        # directory must be writable by the container's mosquitto user. The container runs as that
        # user (1883), so the image's entrypoint does not chown the mounted directory.
        for path in [self.config, *self.config.rglob("*")]:
            os.chmod(path, 0o777 if path.is_dir() else 0o666)
        subprocess.run(["podman", "run", "-d", "--name", self.name, "--user", "1883:1883",
                        "--add-host", f"{ROLE_NAME}:127.0.0.1",
                        "-v", f"{self.config}:/mosquitto/config:Z", self.image], check=True, capture_output=True)
        self.wait_log("listen socket on port 8883")

    def stop(self) -> str:
        for process in self.processes:
            if process.poll() is None:
                process.kill()
        log = self.log()
        subprocess.run(["podman", "rm", "-f", self.name], capture_output=True)
        return log

    def log(self) -> str:
        result = subprocess.run(["podman", "logs", self.name], capture_output=True, text=True)
        return result.stdout + result.stderr

    def wait_log(self, text: str, count: int = 1, timeout: float = 10) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.log().count(text) >= count:
                return True
            time.sleep(0.1)
        return False

    def version(self) -> str:
        result = subprocess.run(["podman", "exec", self.name, "mosquitto", "-h"], capture_output=True, text=True)
        return (result.stdout or result.stderr).splitlines()[0]

    def wearable(self, who: str) -> list[str]:
        return ["-h", ROLE_NAME, "-p", "8883", "-V", "5", "--cafile", f"{CERTS}/ca.crt",
                "--cert", f"{CERTS}/{who}.crt", "--key", f"{CERTS}/{who}.key"]

    def services(self) -> list[str]:
        return ["-h", "127.0.0.1", "-p", "1883", "-V", "5", "-u", SERVICES_USER, "-P", SERVICES_PASSWORD]

    def background(self, label: str, args: list[str], stdin: bool = False) -> subprocess.Popen:
        handle = open(self.out / f"{label}.txt", "w")
        process = subprocess.Popen(["podman", "exec", *(["-i"] if stdin else []), self.name, *args],
                                   stdin=subprocess.PIPE if stdin else None, stdout=handle,
                                   stderr=subprocess.STDOUT, text=True)
        process.label = label
        self.processes.append(process)
        return process

    def output(self, label: str) -> str:
        return (self.out / f"{label}.txt").read_text()

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(["podman", "exec", self.name, *args], capture_output=True, text=True, timeout=30)

    def monitor(self) -> None:
        subscribes = self.log().count("Received SUBSCRIBE")
        self.background("monitor", ["mosquitto_sub", *self.services(), "-q", "1", "-v", "-t", "mm/fixed/#"])
        assert self.wait_log("Received SUBSCRIBE", subscribes + 1), "monitor never subscribed"

    def open_publisher(self, who: str) -> subprocess.Popen:
        """A wearable connection that stays open; each line written to it is published."""
        connects = self.log().count(f"u'{self.material.ids[who]}'")
        process = self.background(f"pub-{who}", ["mosquitto_pub", *self.wearable(who), "-d", "-q", "1", "-l",
                                                 "-t", f"mm/fixed/{self.material.ids[who]}/alert"], stdin=True)
        assert self.wait_log(f"u'{self.material.ids[who]}'", connects + 1), f"{who} never connected"
        return process

    def open_subscriber(self, who: str) -> subprocess.Popen:
        subscribes = self.log().count("Received SUBSCRIBE")
        process = self.background(f"sub-{who}", ["mosquitto_sub", *self.wearable(who), "-d", "-v", "-q", "1",
                                                 "-t", f"mm/fixed/{self.material.ids[who]}/command"])
        self.wait_log("Received SUBSCRIBE", subscribes + 1)
        return process

    def command(self, who: str, text: str) -> None:
        self.run(["mosquitto_pub", *self.services(), "-q", "1",
                  "-t", f"mm/fixed/{self.material.ids[who]}/command", "-m", text])

    def fresh_publish(self, who: str, text: str) -> subprocess.CompletedProcess:
        return self.run(["mosquitto_pub", *self.wearable(who), "-d", "-q", "1",
                         "-t", f"mm/fixed/{self.material.ids[who]}/alert", "-m", text])

    def fresh_subscribe(self, who: str) -> subprocess.CompletedProcess:
        return self.run(["mosquitto_sub", *self.wearable(who), "-d", "-q", "1", "-W", "2", "-C", "1",
                         "-t", f"mm/fixed/{self.material.ids[who]}/command"])


def send(process: subprocess.Popen, text: str) -> None:
    if process.poll() is None:
        try:
            process.stdin.write(text + "\n")
            process.stdin.flush()
        except BrokenPipeError:
            pass


def alive(process: subprocess.Popen) -> bool:
    return process.poll() is None


def mechanism_a(image: str, material: Material, workdir: Path) -> dict:
    a, b = material.ids["a"], material.ids["b"]
    broker = Broker(image, material, workdir, ACL_CONF, {"wearables.acl": wearables_acl([])})
    broker.start()
    result = {"image": image, "version": broker.version(), "mechanism": "A: acl_file deny + SIGHUP"}
    try:
        broker.monitor()
        pub_a, pub_b, sub_a = broker.open_publisher("a"), broker.open_publisher("b"), broker.open_subscriber("a")
        send(pub_a, "a-before")
        send(pub_b, "b-before")
        broker.command("a", "cmd-before")
        time.sleep(1.5)

        (broker.config / "wearables.acl").write_text(wearables_acl([a]))
        reloads = broker.log().count("Reloading config")
        subprocess.run(["podman", "kill", "--signal", "HUP", broker.name], check=True, capture_output=True)
        result["sighup_reloaded"] = broker.wait_log("Reloading config", reloads + 1)
        time.sleep(1)

        send(pub_a, "a-after")
        send(pub_b, "b-after")
        broker.command("a", "cmd-after")
        time.sleep(2)
        monitor = broker.output("monitor")
        result["open_connection"] = {
            "published_before_delivered": "a-before" in monitor,
            "published_after_delivered": "a-after" in monitor,
            "command_before_received": "cmd-before" in broker.output("sub-a"),
            "command_after_received": "cmd-after" in broker.output("sub-a"),
            "publisher_still_connected": alive(pub_a),
            "subscriber_still_connected": alive(sub_a),
        }
        result["other_wearable_unaffected"] = "b-before" in monitor and "b-after" in monitor and alive(pub_b)

        fresh = broker.fresh_publish("a", "a-fresh")
        time.sleep(1)
        result["fresh_connection"] = {
            "connect_accepted": "received CONNACK (0)" in fresh.stdout,
            "publish_delivered": "a-fresh" in broker.output("monitor"),
            "puback": [line for line in fresh.stdout.splitlines() if "PUBACK" in line],
            "suback": [line for line in broker.fresh_subscribe("a").stdout.splitlines() if "Subscribed" in line],
        }

        (broker.config / "wearables.acl").write_text(wearables_acl([]))
        reloads = broker.log().count("Reloading config")
        subprocess.run(["podman", "kill", "--signal", "HUP", broker.name], check=True, capture_output=True)
        broker.wait_log("Reloading config", reloads + 1)
        broker.fresh_publish("a", "a-lifted")
        time.sleep(1)
        result["deny_lifted_publish_delivered"] = "a-lifted" in broker.output("monitor")
    finally:
        log = broker.stop()
        result["broker_disconnect_lines_for_a"] = [line for line in log.splitlines()
                                                   if a in line and "disconnect" in line.lower()]
        (HERE / f"broker-A-{result['version'].split()[-1]}.txt").write_text(log)
        for label in ("monitor", "pub-a", "pub-b", "sub-a"):
            path = broker.out / f"{label}.txt"
            if path.exists():
                (HERE / f"client-A-{result['version'].split()[-1]}-{label}.txt").write_text(path.read_text())
    return result


def dynsec_config(material: Material) -> str:
    def client(name, role):
        return {"username": material.ids[name], "roles": [{"rolename": role}]}
    return json.dumps({
        "defaultACLAccess": {"publishClientSend": False, "publishClientReceive": True,
                             "subscribe": False, "unsubscribe": True},
        "clients": [client("gateway", "admin"), client("a", "wearable"), client("b", "wearable")],
        "groups": [],
        "roles": [
            {"rolename": "admin", "acls": [
                {"acltype": "publishClientSend", "topic": "$CONTROL/dynamic-security/#", "allow": True},
                {"acltype": "publishClientReceive", "topic": "$CONTROL/dynamic-security/#", "allow": True},
                {"acltype": "subscribePattern", "topic": "$CONTROL/dynamic-security/#", "allow": True}]},
            {"rolename": "wearable", "acls": [
                {"acltype": "publishClientSend", "topic": "mm/fixed/%u/alert", "allow": True},
                {"acltype": "subscribePattern", "topic": "mm/fixed/%u/command", "allow": True}]},
        ],
    }, indent=2)


def mechanism_b(image: str, material: Material, workdir: Path) -> dict:
    a = material.ids["a"]
    broker = Broker(image, material, workdir, DYNSEC_CONF, {"dynsec.json": dynsec_config(material)})
    broker.start()
    result = {"image": image, "version": broker.version(), "mechanism": "B: dynamic security plugin"}
    try:
        broker.monitor()
        unknown = broker.fresh_publish("c", "c-unknown")
        time.sleep(1)
        result["unknown_wearable"] = {"connect_accepted": "received CONNACK (0)" in unknown.stdout,
                                      "publish_delivered": "c-unknown" in broker.output("monitor"),
                                      "client_output": unknown.stdout.splitlines()[-3:]}
        pub_a = broker.open_publisher("a")
        send(pub_a, "a-before")
        time.sleep(1)
        result["known_wearable_publish_delivered"] = "a-before" in broker.output("monitor")

        ctrl = broker.run(["mosquitto_ctrl", "-h", ROLE_NAME, "-p", "8883", "--cafile", f"{CERTS}/ca.crt",
                           "--cert", f"{CERTS}/gateway.crt", "--key", f"{CERTS}/gateway.key",
                           "dynsec", "disableClient", a])
        result["disable_command"] = {"exit_code": ctrl.returncode, "output": (ctrl.stdout + ctrl.stderr).strip()}
        time.sleep(2)
        send(pub_a, "a-after")
        time.sleep(1)
        result["after_disable"] = {"open_connection_dropped": not alive(pub_a),
                                   "published_after_delivered": "a-after" in broker.output("monitor")}
        fresh = broker.fresh_publish("a", "a-fresh")
        time.sleep(1)
        result["after_disable"].update({"fresh_connect_accepted": "received CONNACK (0)" in fresh.stdout,
                                        "fresh_publish_delivered": "a-fresh" in broker.output("monitor"),
                                        "fresh_output": fresh.stdout.splitlines()[-3:]})
    finally:
        log = broker.stop()
        (HERE / f"broker-B-{result['version'].split()[-1]}.txt").write_text(log)
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mm-spike-") as tmp:
        workdir = Path(tmp)
        material = Material(workdir)
        results = {"ids": material.ids, "runs": []}
        for image in IMAGES:
            results["runs"].append(mechanism_a(image, material, workdir))
            results["runs"].append(mechanism_b(image, material, workdir))
    (HERE / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
