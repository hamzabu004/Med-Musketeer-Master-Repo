import json
import struct
import uuid
from pathlib import Path

import pytest

from mmca.core.ca import init_ca, issue_device
from mmca.core.config import ensure_layout
from mmca.core.errors import MMCAError, SafetyError
from mmca.core.flash import (ESP_ERASE_PHRASES, PARTITION_MAGIC, PARTITION_TABLE_READ_SIZE,
                             choose_port, erase_esp, flash_device, parse_partition_table)

PASSPHRASE = "local-test-ca-passphrase"
PARTITION_OFFSET = 0x1D0000
PARTITION_SIZE = 0x30000
NVS_OFFSET = 0x9000
NVS_SIZE = 0x6000


def _entry(name, offset, size):
    return struct.pack("<HBBII16sI", PARTITION_MAGIC, 1, 2, offset, size,
                       name.encode().ljust(16, b"\0"), 0)


def partition_table(*, include_creds=True, include_nvs=False):
    entries = b""
    if include_nvs:
        entries += _entry("nvs", NVS_OFFSET, NVS_SIZE)
    if include_creds:
        entries += _entry("creds", PARTITION_OFFSET, PARTITION_SIZE)
    marker = struct.pack("<H", 0xEBEB) + b"\xff" * 30
    data = entries + marker
    return data + b"\xff" * (PARTITION_TABLE_READ_SIZE - len(data))


def setup_wearable(settings):
    ensure_layout(settings)
    init_ca(settings, "MedMusketeer CA", 3650, PASSPHRASE)
    device_id = str(uuid.uuid4())
    issue_device(settings, "wearable", device_id, "ec_p256", 365, PASSPHRASE,
                 confirm=lambda _preview: True)
    return device_id


def ports():
    return [{"device": "/dev/fake-esp", "description": "test board", "vid_pid": "303A:1001"}]


def run_mocked_flash(monkeypatch, settings, device_id, *, chip="ESP32-S3", include_creds=True,
                     mismatch=False):
    import mmca.core.flash as flash
    state = {"written": None}

    def fake_run(port, *args):
        if args[0] == "chip-id":
            return f"Chip is {chip} (revision v0.2)\nMAC: AA:BB:CC:DD:EE:FF"
        if args[0] == "flash-id":
            return "Manufacturer: Winbond\nDetected flash size: 2MB"
        if args[0] == "read-flash" and args[1] == "0x8000":
            Path(args[3]).write_bytes(partition_table(include_creds=include_creds))
            return "read partition table"
        if args[0] == "write-flash":
            state["written"] = Path(args[2]).read_bytes()
            return "written"
        if args[0] == "read-flash":
            data = state["written"] or b"\xff" * int(args[2], 16)
            if mismatch:
                data = b"bad" + data[3:]
            Path(args[3]).write_bytes(data)
            return "read credentials"
        raise AssertionError(args)

    monkeypatch.setattr(flash, "_run_esptool", fake_run)
    return flash_device(settings, device_id, "/dev/fake-esp", input_fn=lambda _prompt: "y",
                        output_fn=lambda *_: None, ports_fn=ports)


def test_partition_table_parser_reads_named_nvs_partition():
    parsed = parse_partition_table(partition_table())
    assert len(parsed) == 1
    assert parsed[0].name == "creds"
    assert parsed[0].offset == PARTITION_OFFSET
    assert parsed[0].size == PARTITION_SIZE


def test_serial_port_selection_never_auto_picks_among_multiple_ports():
    candidates = ports() + [{"device": "/dev/ttyACM1", "description": "second board",
                             "vid_pid": "10C4:EA60"}]
    with pytest.raises(Exception, match="Invalid serial port selection"):
        choose_port(None, candidates, input_fn=lambda _prompt: "", output_fn=lambda *_: None)
    selected = choose_port(None, candidates, input_fn=lambda _prompt: "2", output_fn=lambda *_: None)
    assert selected == "/dev/ttyACM1"


def test_flash_builds_nvs_writes_verifies_then_removes_key(settings, monkeypatch):
    device_id = setup_wearable(settings)
    result = run_mocked_flash(monkeypatch, settings, device_id)
    issued = settings.issued_dir / device_id
    assert result["partition_offset"] == PARTITION_OFFSET
    assert result["chip_mac"] == "AA:BB:CC:DD:EE:FF"
    assert not (issued / "device.key").exists()
    meta = json.loads((issued / "meta.json").read_text())
    assert meta["flashed"] is True


def test_wrong_chip_stops_without_removing_private_key(settings, monkeypatch):
    device_id = setup_wearable(settings)
    with pytest.raises(SafetyError, match="not an ESP32-S3"):
        run_mocked_flash(monkeypatch, settings, device_id, chip="ESP32")
    assert (settings.issued_dir / device_id / "device.key").exists()


def test_missing_partition_stops_without_removing_private_key(settings, monkeypatch):
    device_id = setup_wearable(settings)
    with pytest.raises(SafetyError, match="No `creds` partition"):
        run_mocked_flash(monkeypatch, settings, device_id, include_creds=False)
    assert (settings.issued_dir / device_id / "device.key").exists()


def test_readback_mismatch_retains_private_key_and_metadata(settings, monkeypatch):
    device_id = setup_wearable(settings)
    with pytest.raises(SafetyError, match="hash mismatch"):
        run_mocked_flash(monkeypatch, settings, device_id, mismatch=True)
    issued = settings.issued_dir / device_id
    assert (issued / "device.key").exists()
    assert json.loads((issued / "meta.json").read_text())["flashed"] is False


def flashed_wearable(settings, *, chip_mac="AA:BB:CC:DD:EE:FF"):
    device_id = setup_wearable(settings)
    meta_path = settings.issued_dir / device_id / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta.update({"flashed": True, "chip_mac": chip_mac})
    meta_path.write_text(json.dumps(meta))
    return device_id, meta_path


def run_mocked_erase(monkeypatch, settings, device_id, target, *, include_nvs=True,
                     dirty=False, phrase=None):
    import mmca.core.flash as flash
    calls = []

    def fake_run(port, *args, after=None):
        calls.append((args, after))
        if args[0] == "chip-id":
            return "Chip type: ESP32-S3 (QFN56)\nMAC: AA:BB:CC:DD:EE:FF"
        if args[0] == "flash-id":
            return "Detected flash size: 16MB"
        if args[0] == "read-flash" and args[1] == "0x8000":
            Path(args[3]).write_bytes(partition_table(include_nvs=include_nvs))
            return "read partition table"
        if args[0] == "erase-region":
            return "erased"
        if args[0] == "read-flash":
            size = int(args[2], 16)
            Path(args[3]).write_bytes((b"\xfe" if dirty else b"\xff") * size)
            return "read back"
        raise AssertionError(args)

    monkeypatch.setattr(flash, "_run_esptool", fake_run)
    answer = phrase if phrase is not None else ESP_ERASE_PHRASES[target]
    result = None
    try:
        result = erase_esp(settings, device_id, "/dev/fake-esp", target=target,
                           input_fn=lambda _prompt: answer, output_fn=lambda *_: None,
                           ports_fn=ports)
    finally:
        run_mocked_erase.calls = calls
    return result, calls


@pytest.mark.parametrize("target, regions", [
    ("tls", [(PARTITION_OFFSET, PARTITION_SIZE)]),
    ("network", [(NVS_OFFSET, NVS_SIZE)]),
    ("all", [(NVS_OFFSET, NVS_SIZE), (PARTITION_OFFSET, PARTITION_SIZE)]),
])
def test_erase_esp_erases_selected_partitions_without_rebooting_before_verify(
        settings, monkeypatch, target, regions):
    device_id, meta_path = flashed_wearable(settings)
    result, calls = run_mocked_erase(monkeypatch, settings, device_id, target)
    erases = [(args, after) for args, after in calls if args[0] == "erase-region"]
    assert [(int(a[1], 16), int(a[2], 16)) for a, _ in erases] == regions
    assert all(after == "no-reset" for _, after in erases)
    readbacks = [after for args, after in calls if args[0] == "read-flash" and args[1] != "0x8000"]
    assert readbacks == ["no-reset"] * (len(regions) - 1) + [None]
    assert [p["offset"] for p in result["partitions"]] == [offset for offset, _ in regions]
    meta = json.loads(meta_path.read_text())
    assert meta.get("credentials_erased", False) is (target in ("tls", "all"))
    assert meta.get("network_erased", False) is (target in ("network", "all"))
    audit = [json.loads(line) for line in settings.audit_path.read_text().splitlines()]
    assert audit[-1]["action"] == "erase_esp"
    assert audit[-1]["details"]["target"] == target


def test_erase_esp_verification_failure_leaves_metadata_unchanged(settings, monkeypatch):
    device_id, meta_path = flashed_wearable(settings)
    with pytest.raises(SafetyError, match="verification failed"):
        run_mocked_erase(monkeypatch, settings, device_id, "network", dirty=True)
    assert "network_erased" not in json.loads(meta_path.read_text())


def test_erase_esp_wrong_phrase_erases_nothing(settings, monkeypatch):
    device_id, _ = flashed_wearable(settings)
    with pytest.raises(MMCAError, match="cancelled"):
        run_mocked_erase(monkeypatch, settings, device_id, "all",
                         phrase=ESP_ERASE_PHRASES["tls"])
    assert not any(args[0] == "erase-region" for args, _ in run_mocked_erase.calls)


@pytest.mark.parametrize("target", ["network", "all"])
def test_erase_esp_requires_app_nvs_partition(settings, monkeypatch, target):
    device_id, _ = flashed_wearable(settings)
    with pytest.raises(SafetyError, match="nvs"):
        run_mocked_erase(monkeypatch, settings, device_id, target, include_nvs=False)
    assert not any(args[0] == "erase-region" for args, _ in run_mocked_erase.calls)


def test_erase_esp_refuses_different_chip_mac(settings, monkeypatch):
    device_id, _ = flashed_wearable(settings, chip_mac="11:22:33:44:55:66")
    with pytest.raises(SafetyError, match="MAC"):
        run_mocked_erase(monkeypatch, settings, device_id, "network")
    assert not any(args[0] == "erase-region" for args, _ in run_mocked_erase.calls)
