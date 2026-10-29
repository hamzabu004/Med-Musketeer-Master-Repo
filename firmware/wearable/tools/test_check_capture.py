"""TC-W01 (host part) and TC-W04: the firmware's alert passes the cloud contract; the checker refuses
what ingestion would. Run with the cloud backend's environment:

    cloud/backend/.venv/bin/python -m pytest firmware/wearable/tools

The host build needs gcc and cJSON's source: the ESP-IDF managed component after `idf.py build`,
or a directory named by MM_CJSON_DIR (CI clones cJSON there). Without them that test is skipped.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
WEARABLE = TOOLS.parent
REPO = WEARABLE.parents[1]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO / "cloud" / "backend"))
from check_capture import check  # noqa: E402
from tests.messages import alert_payload, status_payload  # noqa: E402

DEVICE = "8f0f5194-93bf-4e1d-8e72-f96fa1f3df21"


def line(msg_type: str, payload: dict, device: str = DEVICE) -> str:
    return f"mm/fixed/{device}/{msg_type} {json.dumps(payload)}"


def cjson_dir() -> Path | None:
    if os.environ.get("MM_CJSON_DIR"):
        return Path(os.environ["MM_CJSON_DIR"])
    found = sorted((WEARABLE / "managed_components").glob("espressif__cjson/**/cJSON.c"))
    return found[0].parent if found else None


def test_tc_w01_firmware_alert_passes_the_contract(tmp_path):
    source = cjson_dir()
    if not shutil.which("gcc") or not source or not (source / "cJSON.c").exists():
        pytest.skip("needs gcc and cJSON's source (idf.py build, or MM_CJSON_DIR)")
    binary = tmp_path / "alert_host"
    subprocess.run(["gcc", "-Wall", "-Wextra", "-Werror", f"-I{TOOLS / 'host_stubs'}", f"-I{WEARABLE / 'main'}",
                    f"-I{source}", str(TOOLS / "host_stubs" / "main.c"), str(WEARABLE / "main" / "alert.c"),
                    str(source / "cJSON.c"), "-lm", "-o", str(binary)], check=True)
    lines = subprocess.run([str(binary), DEVICE], check=True, capture_output=True, text=True).stdout.splitlines()

    report = check(lines, DEVICE)
    assert report.errors == []
    assert report.counts == {"alert": 2, "status": 0}
    first = json.loads(lines[0].partition(" ")[2])
    assert (first["fs_hz"], first["n_samples"], first["lead"]) == (360, 1080, "SYNTH")
    assert first["screening"] == {"label": "abnormal", "confidence": 1, "model": "button-stub-0"}
    assert len(lines[0]) < 4096 - 64, "must fit the firmware's 4096-byte MQTT buffer"


def test_tc_w04_valid_capture_passes():
    report = check([line("status", status_payload()), line("alert", alert_payload(seq=0)),
                    line("alert", alert_payload(seq=1)), line("status", status_payload("offline"))], DEVICE)
    assert report.errors == []
    assert report.counts == {"alert": 2, "status": 2}


def test_tc_w04_reboot_restarts_seq():
    assert check([line("alert", alert_payload(seq=5)), line("alert", alert_payload(seq=0))]).errors == []


@pytest.mark.parametrize("lines, reason", [
    ([line("alert", {"device_id": DEVICE, "type": "test_alert", "message": "Periodic ESP32 test alert",
                     "timestamp": 1761100000})], "alert is not valid"),
    ([line("alert", alert_payload(n_samples=10, samples=alert_payload()["samples"]))], "alert is not valid"),
    ([line("alert", alert_payload(), device="someone-else")], "expected"),
    ([line("telemetry", {})], "unexpected topic"),
    ([line("status", status_payload(revocation_version=3))], "revocation_version"),
    ([line("alert", alert_payload(seq=1)), line("alert", alert_payload(seq=3))], "seq 3 follows 1"),
    ([line("alert", alert_payload(msg_id="0b9d2c55-3bb5-4c4b-9e57-2a43a5d6a6c1", seq=0)),
      line("alert", alert_payload(msg_id="0b9d2c55-3bb5-4c4b-9e57-2a43a5d6a6c1", seq=1))], "repeats"),
    ([line("alert", alert_payload(segment_start="2026-10-30T12:00:05Z", sent_at="2026-10-30T12:00:00Z"))],
     "later than sent_at"),
    (["mm/fixed/x/alert not-json"], "alert is not valid"),
])
def test_tc_w04_checker_refuses(lines, reason):
    errors = check(lines, DEVICE).errors
    assert errors and reason in errors[-1]
