"""Iteration 4, Slice 0 spike: the EMQX side of the revocation list (cloud-backend.md D16).

Run with any Python 3.11+ (standard library only):
    python3 docs/testing/evidence/2026-10-29/revocation-spike/spike_emqx.py

Needs Docker with emqx/emqx:6.3.2 (the pinned image, D10) and podman with eclipse-mosquitto:2 for
the MQTT clients. Writes emqx-results.json next to this file.

Checks, once with the retainer in RAM (EMQX's default) and once on disc:
- an API key bootstrapped from a file (`api_key.bootstrap_file`) authenticates the REST API;
- a retained REST publish (`POST /api/v5/publish`) is delivered although client authorisation
  denies every publish (`no_match = deny`), as with the API's hook for this topic;
- a client cannot overwrite the retained list;
- a client is found by username and disconnected (`GET /api/v5/clients?username=`,
  `DELETE /api/v5/clients/{clientid}`);
- whether the retained message survives the container being recreated on the same data volume,
  as `docker compose up` does after an image change.
"""
import base64
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
IMAGE = "emqx/emqx:6.3.2"
CLIENT_IMAGE = "docker.io/library/eclipse-mosquitto:2"
API_PORT, MQTT_PORT = 18183, 21883
KEY, SECRET = "mm-spike", "spike-secret-0123456789abcdef"
TOPIC = "mm/revocations/wearables"
ACL = '{allow, all, subscribe, ["#"]}.\n{deny, all}.\n'


def api(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    request = urllib.request.Request(f"http://127.0.0.1:{API_PORT}/api/v5{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
    request.add_header("Authorization", "Basic " + base64.b64encode(f"{KEY}:{SECRET}".encode()).decode())
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read().decode()
            return response.status, json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def mqtt(tool: str, *args: str, background: bool = False, out: Path | None = None, name: str | None = None):
    # A killed `podman run` leaves its container running, so background clients are named and
    # removed by that name.
    command = ["podman", "run", "--rm", "--network", "host", *(["--name", name] if name else []), CLIENT_IMAGE, tool,
               "-h", "127.0.0.1", "-p", str(MQTT_PORT), "-V", "5", *args]
    if background:
        return subprocess.Popen(command, stdout=open(out, "w"), stderr=subprocess.STDOUT, text=True)
    return subprocess.run(command, capture_output=True, text=True, timeout=30)


def start(name: str, workdir: Path, volume: str, storage: str) -> None:
    # Docker Desktop cannot bind-mount /tmp, so the two files are copied in before the start.
    subprocess.run(["docker", "create", "--name", name,
                    "-p", f"127.0.0.1:{API_PORT}:18083", "-p", f"127.0.0.1:{MQTT_PORT}:1883",
                    "-v", f"{volume}:/opt/emqx/data",
                    "-e", "EMQX_NODE__NAME=emqx@127.0.0.1", "-e", "EMQX_NODE__COOKIE=spike",
                    "-e", "EMQX_API_KEY__BOOTSTRAP_FILE=/opt/emqx/etc/mm_api_keys.txt",
                    "-e", f"EMQX_RETAINER__BACKEND__STORAGE_TYPE={storage}",
                    "-e", "EMQX_AUTHORIZATION__NO_MATCH=deny",
                    "-e", "EMQX_AUTHORIZATION__CACHE__ENABLE=false",
                    "-e", 'EMQX_AUTHORIZATION__SOURCES=[{type=file,path="/opt/emqx/etc/mm_acl.conf"}]',
                    IMAGE], check=True, capture_output=True)
    for source, target in (("api_keys.txt", "mm_api_keys.txt"), ("acl.conf", "mm_acl.conf")):
        subprocess.run(["docker", "cp", str(workdir / source), f"{name}:/opt/emqx/etc/{target}"],
                       check=True, capture_output=True)
    subprocess.run(["docker", "start", name], check=True, capture_output=True)
    deadline = time.time() + 90
    while time.time() < deadline:
        try:
            if api("GET", "/clients")[0] == 200:
                return
        except (urllib.error.URLError, ConnectionError, OSError):
            pass
        time.sleep(1)
    raise RuntimeError("EMQX API never answered with the bootstrapped key")


def retained() -> str | None:
    status, body = api("GET", f"/mqtt/retainer/message/{urllib.parse.quote(TOPIC, safe='')}")
    return base64.b64decode(body["payload"]).decode() if status == 200 else None


def run(storage: str, workdir: Path) -> dict:
    name, volume = f"mm-emqx-spike-{storage}", f"mm-emqx-spike-{storage}"
    subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True)
    result = {"storage_type": storage}
    start(name, workdir, volume, storage)
    try:
        result["api_key_bootstrap_authenticates"] = True
        out = workdir / f"sub-{storage}.txt"
        clientid = f"gw-client-{storage}"
        listener_name = f"mm-emqx-spike-sub-{storage}"
        mqtt("mosquitto_sub", "-d", "-i", clientid, "-u", "gw-test", "-q", "1", "-v",
             "-t", TOPIC, background=True, out=out, name=listener_name)
        time.sleep(3)
        status, _ = api("POST", "/publish", {"topic": TOPIC, "payload": '{"version":1}', "qos": 1, "retain": True})
        result["rest_publish_status"] = status
        time.sleep(1)
        result["rest_publish_delivered_despite_deny"] = '{"version":1}' in out.read_text()

        forged = mqtt("mosquitto_pub", "-d", "-u", "gw-other", "-q", "1", "-r", "-t", TOPIC, "-m", '{"version":0}')
        time.sleep(1)
        result["client_publish_puback"] = [line for line in forged.stdout.splitlines() if "PUBACK" in line]
        result["retained_after_client_attempt"] = retained()

        status, body = api("GET", "/clients?username=gw-test")
        before = {c["clientid"]: c["connected_at"] for c in body["data"]} if status == 200 else {}
        result["clients_found_by_username"] = sorted(before)
        result["kick_status"] = [api("DELETE", f"/clients/{urllib.parse.quote(c, safe='')}")[0] for c in before]
        time.sleep(0.5)
        status, body = api("GET", "/clients?username=gw-test")
        after = {c["clientid"]: c["connected_at"] for c in body["data"]} if status == 200 else {}
        # mosquitto_sub reconnects on its own, like a gateway would; a revoked gateway's
        # reconnect is then refused by the authentication hook, which this spike does not run.
        result["after_kick"] = {"connected_at_before": before, "connected_at_after": after,
                                "old_session_closed": all(after.get(c) != t for c, t in before.items())}
        subprocess.run(["podman", "rm", "-f", listener_name], capture_output=True)
        result["kicked_client_output"] = [line for line in out.read_text().splitlines() if "DISCONNECT" in line]

        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)
        start(name, workdir, volume, storage)
        result["retained_after_recreate"] = retained()
        fresh = mqtt("mosquitto_sub", "-u", "gw-test", "-q", "1", "-v", "-W", "3", "-C", "1", "-t", TOPIC)
        result["new_subscriber_gets_list_after_recreate"] = '{"version":1}' in fresh.stdout
        shown = subprocess.run(["docker", "exec", name, "emqx", "ctl", "conf", "show", "retainer"],
                               capture_output=True, text=True).stdout
        result["retainer_storage_type_reported"] = [line.strip() for line in shown.splitlines() if "storage_type" in line]
    finally:
        logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
        (HERE / f"emqx-{storage}.txt").write_text(logs.stdout + logs.stderr)
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        subprocess.run(["docker", "volume", "rm", "-f", volume], capture_output=True)
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="mm-emqx-spike-") as tmp:
        workdir = Path(tmp)
        (workdir / "api_keys.txt").write_text(f"{KEY}:{SECRET}:administrator\n")
        (workdir / "acl.conf").write_text(ACL)
        for path in workdir.iterdir():
            path.chmod(0o644)
        workdir.chmod(0o755)
        results = {"image": IMAGE, "runs": [run("ram", workdir), run("disc", workdir)]}
    (HERE / "emqx-results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
