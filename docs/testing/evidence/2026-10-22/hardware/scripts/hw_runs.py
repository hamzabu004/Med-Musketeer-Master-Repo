"""Drive the CA tool against the attached ESP32-S3 with a scratch CA and record the results.

Usage: hw_runs.py <case> <evidence-dir>   case: p03 | a07 | erase-network | erase-tls | erase-all
"""
import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509

from mmca.core.ca import init_ca, issue_device
from mmca.core.config import ensure_layout, load_settings
from mmca.core.errors import MMCAError
from mmca.core.flash import ESP_ERASE_PHRASES, erase_esp, flash_device

HERE = Path(__file__).resolve().parent
PORT = "/dev/ttyACM0"
PASSPHRASE = "scratch-hw-test-passphrase"
ESPTOOL = str(Path(sys.executable).parent / "esptool")
GEN = Path.home() / "esp/esp-idf/components/partition_table/gen_esp32part.py"
CREDS = (0x1D0000, 0x30000)
STATE = HERE / "state.json"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Record:
    def __init__(self, case, evidence):
        self.case, self.evidence, self.lines = case, evidence, []
        self.data = {"case": case, "started": now(), "port": PORT, "steps": []}

    def say(self, text):
        line = f"[{now()}] {text}"
        print(line)
        self.lines.append(line)

    def step(self, name, **values):
        self.data["steps"].append({"step": name, **values})
        self.say(f"{name}: {json.dumps(values)}")

    def save(self, result):
        self.data["result"], self.data["finished"] = result, now()
        self.evidence.mkdir(parents=True, exist_ok=True)
        (self.evidence / f"{self.case}.json").write_text(json.dumps(self.data, indent=2))
        (self.evidence / f"{self.case}.txt").write_text("\n".join(self.lines) + "\n")


def esptool(*args):
    result = subprocess.run([ESPTOOL, "--port", PORT, "-b", "921600", *args],
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def read_region(offset, size):
    path = HERE / f"read_{offset:x}.bin"
    esptool("read-flash", hex(offset), hex(size), str(path))
    data = path.read_bytes()
    path.unlink()
    return data


def boot_log(rec, name, seconds=25):
    out = rec.evidence / f"{rec.case}_{name}_serial.txt"
    subprocess.run([sys.executable, str(HERE / "serial_log.py"), PORT, str(seconds), str(out)],
                   check=True, capture_output=True)
    text = out.read_text()
    assert "PRIVATE KEY" not in text and "BEGIN" not in text
    return text


def scratch():
    settings = load_settings(HERE / "scratch-ca")
    if not (settings.ca_dir / "ca.crt").exists():
        ensure_layout(settings)
        init_ca(settings, "MedMusketeer Scratch Test CA", 30, PASSPHRASE)
    return settings


def new_wearable(settings):
    device_id = str(uuid.uuid4())
    issue_device(settings, "wearable", device_id, "ec_p256", 30, PASSPHRASE,
                 confirm=lambda _preview: True)
    return device_id


def answers(rec, reply):
    def ask(prompt):
        rec.say(f"prompt: {prompt.strip()} -> {reply}")
        return reply
    return ask


def case_p03(rec):
    settings = scratch()
    device_id = new_wearable(settings)
    directory = settings.issued_dir / device_id
    cert_pem = (directory / "device.crt").read_bytes()
    rec.step("issued scratch wearable", device_id=device_id,
             cert_sha256=hashlib.sha256(cert_pem).hexdigest())
    start = time.time()
    result = flash_device(settings, device_id, PORT, input_fn=answers(rec, "y"), output_fn=rec.say)
    rec.step("mmca flash", seconds=round(time.time() - start, 1), **result)
    meta = json.loads((directory / "meta.json").read_text())
    key_removed = not (directory / "device.key").exists()
    rec.step("local state", key_removed=key_removed, flashed=meta["flashed"], chip_mac=meta["chip_mac"])
    image = read_region(*CREDS)
    ca_pem = (settings.ca_dir / "ca.crt").read_bytes()
    rec.step("independent read of creds partition", sha256=hashlib.sha256(image).hexdigest(),
             device_cert_present=cert_pem.rstrip(b"\n") in image,
             ca_cert_present=ca_pem.rstrip(b"\n") in image)
    audit = [e for e in json.loads("[" + ",".join(settings.audit_path.read_text().splitlines()) + "]")
             if e["device_id"] == device_id]
    rec.step("audit", events=[(e["action"], e["result"]) for e in audit])
    log = boot_log(rec, "boot")
    loaded = "Loaded TLS credentials from the read-only creds partition" in log
    topic = f"mm/fixed/{device_id}/alert" in log
    rec.step("boot log", creds_loaded=loaded, alert_topic_uses_new_cn=topic)
    STATE.write_text(json.dumps({"flashed_device": device_id}))
    ok = key_removed and meta["flashed"] and loaded and topic and result["partition_offset"] == CREDS[0]
    return "pass" if ok else "fail"


def case_a07(rec):
    settings = scratch()
    before = hashlib.sha256(read_region(*CREDS)).hexdigest()
    original_table = read_region(0x8000, 0xC00)
    csv = HERE / "single_app.csv"
    csv.write_text("nvs,data,nvs,0x9000,0x6000,\nphy_init,data,phy,0xf000,0x1000,\n"
                   "factory,app,factory,0x10000,0x1C0000,\n")
    table = HERE / "single_app.bin"
    subprocess.run([sys.executable, str(GEN), "-q", str(csv), str(table)], check=True)
    esptool("write-flash", "0x8000", str(table))
    rec.step("wrote partition table without creds", table_sha256=hashlib.sha256(table.read_bytes()).hexdigest())
    device_id = new_wearable(settings)
    directory = settings.issued_dir / device_id
    error = None
    try:
        flash_device(settings, device_id, PORT, input_fn=answers(rec, "y"), output_fn=rec.say)
    except MMCAError as exc:
        error = f"{type(exc).__name__}: {exc}"
    meta = json.loads((directory / "meta.json").read_text())
    key_kept = (directory / "device.key").exists()
    after = hashlib.sha256(read_region(*CREDS)).hexdigest()
    rec.step("mmca flash", device_id=device_id, error=error, key_kept=key_kept,
             flashed=meta["flashed"], creds_region_unchanged=before == after)
    restore = HERE / "ptable_restore.bin"
    restore.write_bytes(original_table)
    esptool("write-flash", "0x8000", str(restore))
    restored = read_region(0x8000, 0xC00) == original_table
    rec.step("restored original partition table", identical=restored)
    ok = error and "No `creds` partition" in error and key_kept and not meta["flashed"] and before == after
    return "pass" if ok and restored else "fail"


def case_erase(rec, scope):
    settings = scratch()
    device_id = json.loads(STATE.read_text())["flashed_device"]
    start = time.time()
    result = erase_esp(settings, device_id, PORT, target=scope,
                       input_fn=answers(rec, ESP_ERASE_PHRASES[scope]), output_fn=rec.say)
    rec.step("mmca erase esp " + scope, seconds=round(time.time() - start, 1),
             partitions=[{"name": p["name"], "offset": hex(p["offset"])} for p in result["partitions"]])
    blank = {}
    for partition in result["partitions"]:
        data = read_region(partition["offset"], partition["size"]) if "size" in partition else None
        if data is not None:
            blank[partition["name"]] = data == b"\xff" * len(data)
    rec.step("independent blank check", **blank)
    log = boot_log(rec, "boot")
    rec.step("boot log", creds_loaded="Loaded TLS credentials" in log,
             saved_wifi_used="Using saved Wi-Fi provisioning" in log,
             advertising="BLE provisioning active" in log)
    return "pass" if all(blank.values()) else "fail"


if __name__ == "__main__":
    case, evidence = sys.argv[1], Path(sys.argv[2])
    rec = Record(case, evidence)
    try:
        if case == "p03":
            outcome = case_p03(rec)
        elif case == "a07":
            outcome = case_a07(rec)
        else:
            outcome = case_erase(rec, case.split("-", 1)[1])
    except Exception as exc:
        rec.say(f"ERROR {type(exc).__name__}: {exc}")
        outcome = "error"
    rec.save(outcome)
    print("RESULT", case, outcome)
