"""TC-B05 to TC-B08: the uplink enforcing the wearable revocation list on a real Mosquitto 2.0.21.

The cases run in order on one gateway broker, one cloud stand-in and one set of wearables
(tests/brokers.py). Set MM_EVIDENCE_DIR to keep the broker logs, the client output and
tc_b05_b08_uplink.json. On the Pi itself these cases are procedure H-B06 (hardware_test_procedures.md).
"""
import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from mm_uplink.config import Config
from mm_uplink.service import Uplink
from tests.brokers import CloudBroker, GatewayBroker, Material, podman_available
from tests.test_revocations import listing

pytestmark = [pytest.mark.interop,
              pytest.mark.skipif(not podman_available(), reason="podman with eclipse-mosquitto:2.0.21 not available")]

EVIDENCE = Path(os.environ["MM_EVIDENCE_DIR"]) if os.environ.get("MM_EVIDENCE_DIR") else None
DENIED = "RC:135"  # MQTT 5 PUBACK 0x87, Not authorized
RECORD: dict = {}


def wait(condition, timeout: float = 10, step: float = 0.1) -> float | None:
    """Seconds until `condition()` held, or None on timeout."""
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if condition():
            return time.monotonic() - started
        time.sleep(step)
    return None


class World:
    def __init__(self, workdir: Path):
        self.material = Material(workdir)
        self.ids = self.material.ids
        self.gateway = GatewayBroker(workdir, self.material)
        self.cloud = CloudBroker(workdir, self.material)
        self.workdir = workdir
        self.uplink: Uplink | None = None

    def config(self) -> Config:
        certs = self.material.certs
        return Config(cloud_host="127.0.0.1", cloud_port=self.cloud.port, cloud_name="cloud.medmusketeer.local",
                      ca_file=certs / "ca.crt", cert_file=certs / "gateway.crt", key_file=certs / "gateway.key",
                      state_file=self.gateway.state / "revocations.json", acl_file=self.gateway.acl,
                      mosquitto_pid_file=self.workdir / "unused.pid",
                      reload_command=tuple(self.gateway.reload_command), retry_s=1)

    def start_uplink(self) -> Uplink:
        self.uplink = Uplink(self.config())
        self.uplink.start()
        return self.uplink

    def stop_uplink(self) -> None:
        if self.uplink:
            self.uplink.stop()
            self.uplink = None

    def reported(self, version: int) -> bool:
        return f'"revocation_version": {version}' in self.cloud.statuses()

    def delivered(self, text: str) -> bool:
        return text in self.gateway.output("monitor")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    world = World(tmp_path_factory.mktemp("uplink"))
    world.cloud.start()
    world.gateway.start()
    world.gateway.monitor()
    yield world
    world.stop_uplink()
    for container in (world.gateway, world.cloud):
        container.remove(EVIDENCE)
    if EVIDENCE:
        (EVIDENCE / "tc_b05_b08_uplink.json").write_text(json.dumps(RECORD, indent=2) + "\n")
        for path in world.gateway.out.glob("*.txt"):
            (EVIDENCE / f"client-{path.name}").write_text(path.read_text())


def send(process, text: str) -> None:
    process.stdin.write(text + "\n")
    process.stdin.flush()


# --- TC-B05 ------------------------------------------------------------------------------------

def test_tc_b05_a_listed_wearable_is_cut_off_on_its_open_connection(world):
    gw, a, b = world.gateway, world.ids["a"], world.ids["b"]
    pub_a, pub_b = gw.open_publisher("a"), gw.open_publisher("b")
    sub_a = gw.open_subscriber("a")
    send(pub_a, "a-before")
    gw.command("a", "cmd-before")
    assert wait(lambda: world.delivered("a-before")) is not None
    assert wait(lambda: "cmd-before" in gw.output("sub-a")) is not None

    uplink = world.start_uplink()
    assert wait(lambda: world.reported(1) is False and "online" in world.cloud.statuses()) is not None  # no list yet
    reloads = gw.log().count("Reloading config")
    started = time.monotonic()
    world.cloud.publish_list(json.dumps(listing(2, a)))
    applied = wait(lambda: uplink.enforcer.enforced_version == 2)
    assert applied is not None and applied < 10
    assert f"user {a}\ntopic deny #" in gw.acl.read_text()
    assert wait(lambda: world.reported(2)) is not None  # the cloud learns the version enforced
    # The uplink counts the list as enforced once it has sent SIGHUP; Mosquitto reloads after that.
    assert gw.wait_log("Reloading config", reloads + 1)
    elapsed = time.monotonic() - started
    assert elapsed < 10

    send(pub_a, "a-after")
    send(pub_b, "b-after")
    gw.command("a", "cmd-after")
    assert wait(lambda: world.delivered("b-after")) is not None
    time.sleep(1)
    assert not world.delivered("a-after")
    assert "cmd-after" not in gw.output("sub-a")
    assert DENIED in gw.fresh_publish("a", "a-fresh")
    assert pub_a.poll() is None and sub_a.poll() is None  # the connection stays open (Slice 0)
    assert uplink.store.listed(a) and not uplink.store.listed(b)
    RECORD["tc_b05"] = {"list_to_enforced_and_reported_s": round(elapsed, 3), "open_connection_cut_off": True,
                        "fresh_connection_puback": DENIED, "other_wearable_unaffected": True}


# --- TC-B06 ------------------------------------------------------------------------------------

def test_tc_b06_older_equal_and_invalid_lists_are_ignored(world):
    uplink, a, b = world.uplink, world.ids["a"], world.ids["b"]
    acl_before = world.gateway.acl.read_text()
    for label, payload in (("older", json.dumps(listing(1, b))), ("equal", json.dumps(listing(2))),
                           ("invalid", "{not json"), ("injection", json.dumps(listing(9, f"{b}\ntopic readwrite #")))):
        world.cloud.publish_list(payload)
        time.sleep(1)
        assert uplink.store.version == 2, label
        assert world.gateway.acl.read_text() == acl_before, label
    assert uplink.store.listed(a) and not uplink.store.listed(b)
    send_ok = world.gateway.fresh_publish("b", "b-check")
    assert DENIED not in send_ok and wait(lambda: world.delivered("b-check")) is not None
    RECORD["tc_b06"] = {"ignored": ["older", "equal", "invalid", "injection"], "version_kept": 2}


# --- TC-B07 ------------------------------------------------------------------------------------

def test_tc_b07_the_stored_list_is_enforced_at_start_before_the_cloud_is_reached(world):
    world.stop_uplink()
    world.cloud.stop()  # the cloud is unreachable from here on
    # A broker that lost the generated file (e.g. setup_mosquitto.sh run again): patterns only.
    from mm_uplink.enforce import PATTERNS
    world.gateway.acl.write_text(PATTERNS)
    world.gateway.acl.chmod(0o600)
    reloads = world.gateway.log().count("Reloading config")
    subprocess.run(world.gateway.reload_command, check=True, capture_output=True)
    assert world.gateway.wait_log("Reloading config", reloads + 1)
    assert "RC:0" in world.gateway.fresh_publish("a", "a-unprotected")  # nothing refuses it now

    uplink = world.start_uplink()
    assert uplink.enforcer.enforced_version == 2  # applied in start(), before any connection
    assert f"user {world.ids['a']}" in world.gateway.acl.read_text()
    assert DENIED in world.gateway.fresh_publish("a", "a-after-restart")
    RECORD["tc_b07"] = {"enforced_version_at_start": 2, "cloud_reachable": False}


# --- TC-B08 ------------------------------------------------------------------------------------

def test_tc_b08_offline_the_list_holds_and_on_reconnect_the_current_one_is_enforced(world):
    gw, a, b, c = world.gateway, world.ids["a"], world.ids["b"], world.ids["c"]
    time.sleep(3)  # well into the outage
    assert DENIED in gw.fresh_publish("a", "a-offline")
    assert DENIED not in gw.fresh_publish("b", "b-offline")
    assert wait(lambda: world.delivered("b-offline")) is not None

    world.cloud.restart()
    started = time.monotonic()
    world.cloud.publish_list(json.dumps(listing(3, c)))  # a lifted, c listed while the gateway was away
    reconnected = wait(lambda: world.uplink.enforcer.enforced_version == 3, timeout=90, step=0.5)
    assert reconnected is not None, "the uplink did not pick up the list after the cloud came back"
    assert wait(lambda: world.reported(3), timeout=10) is not None
    assert DENIED not in gw.fresh_publish("a", "a-lifted")
    assert DENIED in gw.fresh_publish("c", "c-listed")
    assert DENIED not in gw.fresh_publish("b", "b-still")
    RECORD["tc_b08"] = {"offline": {"a": "refused", "b": "accepted"},
                        "cloud_back_to_list_enforced_s": round(time.monotonic() - started, 3),
                        "after_reconnect": {"a": "accepted (lifted)", "c": "refused", "b": "accepted"}}
