"""TC-A08 and TC-P04 against the real Pi with the scratch CA; records results as JSON + text.

Usage: PI_PASS=... hw_pi.py <a08-reject|a08-changed|p04> <evidence-dir>
"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import paramiko

from mmca.core.ca import issue_device
from mmca.core.errors import MMCAError
from mmca.core.ssh import deploy_gateway

sys.path.insert(0, str(Path(__file__).parent))
from hw_runs import PASSPHRASE, Record, scratch  # noqa: E402

HERE = Path(__file__).resolve().parent
HOST, USER = "192.168.50.188", "user-hmz"
STATE = HERE / "pi_state.json"


def remote_fingerprints():
    client = paramiko.SSHClient()
    client.load_host_keys(str(HERE / "known_hosts_pi"))
    client.connect(HOST, username=USER, password=os.environ["PI_PASS"], look_for_keys=False,
                   allow_agent=False)
    stdin, stdout, _ = client.exec_command(
        "sudo -S -p '' sh -c 'cd /etc/mosquitto/certs && sha256sum ca.crt gateway.crt gateway.key "
        "&& stat -c \"%n %U:%G %a\" . ca.crt gateway.crt gateway.key && ls'")
    stdin.write(os.environ["PI_PASS"] + "\n")
    stdin.flush()
    out = stdout.read().decode()
    client.close()
    return out


def gateway_identity(settings):
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    if "gateway" not in state:
        device_id = str(uuid.uuid4())
        issue_device(settings, "gateway", device_id, "ec_p256", 30, PASSPHRASE,
                     confirm=lambda _preview: True)
        state["gateway"] = device_id
        STATE.write_text(json.dumps(state))
    return state["gateway"]


def run_deploy(rec, settings, device_id, known_hosts, answer, restart=False):
    def ask(prompt):
        rec.say(f"prompt: {prompt.strip()} -> {answer}")
        return answer

    def password(prompt):
        rec.say(f"prompt: {prompt.strip()} -> <entered>")
        return os.environ["PI_PASS"]

    try:
        result = deploy_gateway(settings, device_id, HOST, username=USER, restart=restart,
                                input_fn=ask, password_fn=password, output_fn=rec.say,
                                known_hosts=known_hosts)
        return result, None
    except MMCAError as exc:
        return None, f"{type(exc).__name__}: {exc}"


def case_a08_reject(rec):
    settings = scratch()
    device_id = gateway_identity(settings)
    known_hosts = HERE / "a08_known_hosts"
    known_hosts.unlink(missing_ok=True)
    before = remote_fingerprints()
    result, error = run_deploy(rec, settings, device_id, known_hosts, "n")
    after = remote_fingerprints()
    rec.step("deploy to unknown host, approval refused", error=error,
             known_hosts_created=known_hosts.exists(), remote_unchanged=before == after)
    return "pass" if error and "not approved" in error and not known_hosts.exists() and before == after else "fail"


def case_a08_changed(rec):
    settings = scratch()
    device_id = gateway_identity(settings)
    known_hosts = HERE / "a08_known_hosts"
    impostor = paramiko.Ed25519Key.from_private_key_file(str(HERE / "impostor_ed25519"))
    keys = paramiko.HostKeys()
    keys.add(HOST, impostor.get_name(), impostor)
    keys.save(str(known_hosts))
    rec.step("known_hosts holds a different ed25519 key for the Pi",
             saved_fingerprint=f"SHA256:{impostor.fingerprint}")
    before = remote_fingerprints()
    result, error = run_deploy(rec, settings, device_id, known_hosts, "y")
    after = remote_fingerprints()
    rec.step("deploy with changed host key", error=error, remote_unchanged=before == after)
    known_hosts.unlink()
    return "pass" if error and "mismatch" in error and before == after else "fail"


def case_p04(rec):
    settings = scratch()
    device_id = gateway_identity(settings)
    known_hosts = HERE / "a08_known_hosts"
    known_hosts.unlink(missing_ok=True)
    meta = json.loads((settings.issued_dir / device_id / "meta.json").read_text())
    rec.step("scratch gateway identity", device_id=device_id, fingerprint=meta["fingerprint_sha256"])
    result, error = run_deploy(rec, settings, device_id, known_hosts, "y", restart=True)
    rec.step("mmca deploy --restart", result=result, error=error,
             known_hosts_saved=known_hosts.exists())
    remote = remote_fingerprints()
    rec.say("remote state:\n" + remote)
    local = {name: __import__("hashlib").sha256(path.read_bytes()).hexdigest() for name, path in (
        ("ca.crt", settings.ca_dir / "ca.crt"),
        ("gateway.crt", settings.issued_dir / device_id / "device.crt"),
        ("gateway.key", settings.issued_dir / device_id / "device.key"))}
    matches = {name: f"{digest}  {name}" in remote for name, digest in local.items()}
    modes = all(f"{name} root:mosquitto 640" in remote for name in local) and ". root:mosquitto 750" in remote
    audit = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    last = audit[-1]
    rec.step("verification", files_match_local=matches, owner_and_modes_ok=modes,
             audit_last=(last["action"], last["result"], last.get("details", {}).get("host")))
    ok = result and result["restarted"] and all(matches.values()) and modes
    return "pass" if ok else "fail"


if __name__ == "__main__":
    case, evidence = sys.argv[1], Path(sys.argv[2])
    rec = Record(case, evidence)
    try:
        outcome = {"a08-reject": case_a08_reject, "a08-changed": case_a08_changed,
                   "p04": case_p04}[case](rec)
    except Exception as exc:
        rec.say(f"ERROR {type(exc).__name__}: {exc}")
        outcome = "error"
    rec.save(outcome)
    print("RESULT", case, outcome)
