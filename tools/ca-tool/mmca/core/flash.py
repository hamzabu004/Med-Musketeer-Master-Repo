from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

import serial.tools.list_ports
from cryptography import x509

from .audit import append_event
from .config import Settings
from .errors import MMCAError, SafetyError
from .profiles import validate_device_id

PARTITION_TABLE_OFFSET = 0x8000
PARTITION_TABLE_READ_SIZE = 0x1000
PARTITION_ENTRY = 32
PARTITION_MAGIC = 0x50AA
PARTITION_END_MAGIC = 0xEBEB


@dataclass(frozen=True)
class Partition:
    name: str
    type: int
    subtype: int
    offset: int
    size: int


def parse_partition_table(data: bytes) -> list[Partition]:
    entries: list[Partition] = []
    for offset in range(0, len(data) - PARTITION_ENTRY + 1, PARTITION_ENTRY):
        magic = int.from_bytes(data[offset:offset + 2], "little")
        if magic == PARTITION_END_MAGIC:
            return entries
        if magic != PARTITION_MAGIC:
            if data[offset:] == b"\xff" * len(data[offset:]):
                break
            raise SafetyError(f"Invalid partition-table entry at offset 0x{offset:x}")
        entry = data[offset:offset + PARTITION_ENTRY]
        part_type = entry[2]
        subtype = entry[3]
        address = int.from_bytes(entry[4:8], "little")
        size = int.from_bytes(entry[8:12], "little")
        label = entry[12:28].split(b"\0", 1)[0].decode("ascii", errors="strict")
        if not label or size <= 0 or address + size > 0x100000000:
            raise SafetyError("Partition table contains an invalid partition entry")
        entries.append(Partition(label, part_type, subtype, address, size))
    return entries


def _esptool() -> str:
    try:
        __import__("esptool")
    except ImportError as exc:
        raise MMCAError("esptool was not found; install the CA Tool dependencies") from exc
    return sys.executable


def _run_esptool(port: str, *args: str, after: str | None = None) -> str:
    command = [_esptool(), "-m", "esptool", "--port", port]
    if after:
        command += ["--after", after]
    command += list(args)
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise MMCAError("esptool timed out; check the USB connection and retry") from exc
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip().splitlines()
        detail = message[-1] if message else "operation failed"
        raise MMCAError(f"esptool failed: {detail}") from exc
    return result.stdout + "\n" + result.stderr


def list_ports() -> list[dict[str, str | None]]:
    ports = []
    for port in serial.tools.list_ports.comports():
        vidpid = None
        if port.vid is not None and port.pid is not None:
            vidpid = f"{port.vid:04X}:{port.pid:04X}"
        ports.append({"device": port.device, "description": port.description,
                      "vid_pid": vidpid})
    return ports


def choose_port(requested: str | None, ports: list[dict[str, str | None]], *, input_fn=input,
                output_fn=print) -> str:
    if not ports:
        raise MMCAError("No serial ports found; connect the ESP32-S3 and refresh")
    if requested:
        if requested not in {p["device"] for p in ports}:
            raise MMCAError(f"Serial port {requested} is not currently available")
        return requested
    for number, port in enumerate(ports, 1):
        output_fn(f"{number}. {port['device']} — {port['description']} (VID:PID {port['vid_pid'] or 'unknown'})")
    if len(ports) == 1:
        selected = ports[0]["device"]
        if input_fn(f"Use {selected}? [y/N] ").strip().lower() == "y":
            return selected
        raise MMCAError("Port selection cancelled")
    selection = input_fn("Select the serial port number: ").strip()
    if not selection.isdigit() or not 1 <= int(selection) <= len(ports):
        raise MMCAError("Invalid serial port selection")
    return ports[int(selection) - 1]["device"]


def make_nvs_csv(private_key: bytes, device_cert: bytes, ca_cert: bytes, output: Path) -> None:
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["key", "type", "encoding", "value"])
        writer.writerow(["creds", "namespace", "", ""])
        writer.writerow(["device_key", "data", "string", private_key.decode("ascii")])
        writer.writerow(["device_cert", "data", "string", device_cert.decode("ascii")])
        writer.writerow(["ca_cert", "data", "string", ca_cert.decode("ascii")])


def _nvs_generator() -> str:
    try:
        __import__("esp_idf_nvs_partition_gen")
    except ImportError as exc:
        raise MMCAError("NVS partition generator was not found; install the CA Tool dependencies") from exc
    return sys.executable


def _build_nvs_image(private_key: bytes, device_cert: bytes, ca_cert: bytes,
                     partition_size: int, output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="mmca-nvs-") as temporary:
        csv_path = Path(temporary) / "credentials.csv"
        make_nvs_csv(private_key, device_cert, ca_cert, csv_path)
        output_name = output.name
        command = [_nvs_generator(), "-m", "esp_idf_nvs_partition_gen", "generate",
                   csv_path.name, output_name, hex(partition_size), "--outdir", temporary]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=60,
                           cwd=temporary)
        except subprocess.TimeoutExpired as exc:
            raise MMCAError("NVS image generation timed out") from exc
        except subprocess.CalledProcessError as exc:
            # Generator diagnostics may echo CSV values, including private PEM material.
            raise MMCAError("NVS image generation failed; check the firmware partition capacity") from exc
        generated = Path(temporary) / output_name
        if not generated.is_file() or generated.stat().st_size > partition_size:
            raise SafetyError("NVS generator returned an image with an unexpected size")
        shutil.copyfile(generated, output)


def _lookup_nvs_partition(table_data: bytes, name: str) -> Partition:
    matches = [p for p in parse_partition_table(table_data) if p.name == name]
    if not matches:
        raise SafetyError(f"No `{name}` partition found; flash firmware containing it first")
    if len(matches) != 1:
        raise SafetyError(f"Partition table has multiple `{name}` entries")
    partition = matches[0]
    if partition.type != 1 or partition.subtype != 2:
        raise SafetyError(f"`{name}` must be an ESP-IDF data/NVS partition")
    return partition


def _parse_flash_size(output: str) -> int:
    match = re.search(r"Detected flash size:\s*(\d+)\s*(B|KB|MB|GB)\b", output, re.IGNORECASE)
    if not match:
        raise SafetyError("Could not determine ESP32 flash size; refusing to write")
    multiplier = {"b": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}[match.group(2).lower()]
    return int(match.group(1)) * multiplier


def _flash_device(settings: Settings, device_id: str, requested_port: str | None = None,
                  *, input_fn=input, output_fn=print, ports_fn=list_ports) -> dict:
    device_id = validate_device_id(device_id)
    directory = settings.issued_dir / device_id
    try:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        if meta.get("profile") != "wearable":
            raise SafetyError("Only wearable credentials can be flashed to an ESP32-S3")
        key_path = directory / "device.key"
        if key_path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise SafetyError("Wearable private-key permissions are too open; expected mode 600")
        key_data = key_path.read_bytes()
        cert_data = (directory / "device.crt").read_bytes()
        ca_data = (settings.ca_dir / "ca.crt").read_bytes()
        cert = x509.load_pem_x509_certificate(cert_data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, MMCAError):
            raise
        raise MMCAError(f"Cannot load complete wearable credentials for {device_id}") from exc
    if meta.get("flashed"):
        output_fn("Warning: this credential set is marked flashed already.")
    port = choose_port(requested_port, ports_fn(), input_fn=input_fn, output_fn=output_fn)
    info = _run_esptool(port, "chip-id")
    # esptool 5.x reports `Chip type: ESP32-S3`; older releases used
    # `Chip is ESP32-S3`. Accept both while requiring the exact chip family.
    if not re.search(r"\bChip\s+(?:is\s+|type:\s*)ESP32-S3\b", info, re.IGNORECASE):
        raise SafetyError("Connected chip is not an ESP32-S3; no data was written")
    mac_match = re.search(r"MAC:\s*([0-9A-Fa-f:]{17})", info)
    chip_mac = mac_match.group(1).upper() if mac_match else "unknown"
    flash_info = _run_esptool(port, "flash-id")
    flash_size = _parse_flash_size(flash_info)
    output_fn(f"Chip: ESP32-S3; MAC: {chip_mac}; flash: {flash_size} bytes")
    with tempfile.TemporaryDirectory(prefix="mmca-flash-") as temporary:
        table_file = Path(temporary) / "partition-table.bin"
        _run_esptool(port, "read-flash", hex(PARTITION_TABLE_OFFSET),
                     hex(PARTITION_TABLE_READ_SIZE), str(table_file))
        partition = _lookup_nvs_partition(table_file.read_bytes(), settings.creds_partition_name)
        if partition.offset + partition.size > flash_size:
            raise SafetyError("creds partition extends beyond the detected flash size")
        image_file = Path(temporary) / "creds.bin"
        _build_nvs_image(key_data, cert_data, ca_data, partition.size, image_file)
        if image_file.stat().st_size > partition.size:
            raise SafetyError("Credential image exceeds the device's creds partition")
        output_fn(f"Will replace {settings.creds_partition_name} at 0x{partition.offset:X} "
                  f"({partition.size} bytes) on {port} with wearable {device_id}.")
        if input_fn("This overwrites the credentials partition. Continue? [y/N] ").strip().lower() != "y":
            raise MMCAError("Flash cancelled")
        _run_esptool(port, "write-flash", hex(partition.offset), str(image_file))
        readback = Path(temporary) / "readback.bin"
        _run_esptool(port, "read-flash", hex(partition.offset), hex(partition.size), str(readback))
        expected_hash = hashlib.sha256(image_file.read_bytes()).digest()
        actual_hash = hashlib.sha256(readback.read_bytes()).digest()
        if actual_hash != expected_hash:
            raise SafetyError("Flash read-back hash mismatch; key retained and metadata unchanged")
    meta["flashed"] = True
    meta["flashed_at"] = datetime.now(timezone.utc).isoformat()
    meta["flash_port"] = port
    meta["chip_mac"] = chip_mac
    meta["partition_offset"] = f"0x{partition.offset:X}"
    (directory / "meta.json").write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.chmod(directory / "meta.json", 0o600)
    key_path.unlink()
    from cryptography.hazmat.primitives import hashes
    fingerprint = cert.fingerprint(hashes.SHA256()).hex().upper()
    append_event(settings.audit_path, "flash", device_id=device_id, fingerprint=fingerprint,
                 details={"port": port, "chip_mac": chip_mac, "flash_size": flash_size,
                          "partition_offset": f"0x{partition.offset:X}"})
    return {"port": port, "chip_mac": chip_mac, "flash_size": flash_size,
            "partition_offset": partition.offset,
            "partition_size": partition.size, "fingerprint": fingerprint}


def flash_device(settings: Settings, device_id: str, requested_port: str | None = None,
                 *, input_fn=input, output_fn=print, ports_fn=list_ports) -> dict:
    try:
        return _flash_device(settings, device_id, requested_port, input_fn=input_fn,
                             output_fn=output_fn, ports_fn=ports_fn)
    except Exception as exc:
        # Failures are audited without exception text, which can contain local paths.
        try:
            canonical_id = validate_device_id(device_id)
            append_event(settings.audit_path, "flash", device_id=canonical_id,
                         result="failed", details={"reason": type(exc).__name__})
        except Exception:
            pass
        raise


ESP_ERASE_TARGETS = ("tls", "network", "all")
ESP_ERASE_PHRASES = {
    "tls": "ERASE ESP TLS CREDENTIALS",
    "network": "ERASE ESP NETWORK SETTINGS",
    "all": "ERASE ESP TLS AND NETWORK",
}


def _erase_esp(settings: Settings, device_id: str, requested_port: str | None, target: str,
               *, input_fn=input, output_fn=print, ports_fn=list_ports) -> dict:
    if target not in ESP_ERASE_TARGETS:
        raise MMCAError(f"Unknown ESP erase target {target!r}")
    device_id = validate_device_id(device_id)
    directory = settings.issued_dir / device_id
    try:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MMCAError(f"Cannot load issuance metadata for {device_id}") from exc
    if meta.get("profile") != "wearable" or not meta.get("flashed"):
        raise SafetyError("ESP erasure requires a wearable identity previously flashed by mmca")

    port = choose_port(requested_port, ports_fn(), input_fn=input_fn, output_fn=output_fn)
    info = _run_esptool(port, "chip-id")
    if not re.search(r"\bChip\s+(?:is\s+|type:\s*)ESP32-S3\b", info, re.IGNORECASE):
        raise SafetyError("Connected chip is not an ESP32-S3; no data was erased")
    mac_match = re.search(r"MAC:\s*([0-9A-Fa-f:]{17})", info)
    chip_mac = mac_match.group(1).upper() if mac_match else "unknown"
    recorded_mac = str(meta.get("chip_mac", "unknown")).upper()
    if recorded_mac != "UNKNOWN" and chip_mac != "unknown" and recorded_mac != chip_mac:
        raise SafetyError("Connected ESP32-S3 MAC does not match the device recorded for this certificate")

    flash_info = _run_esptool(port, "flash-id")
    flash_size = _parse_flash_size(flash_info)
    output_fn(f"Chip: ESP32-S3; MAC: {chip_mac}; flash: {flash_size} bytes")
    names = {"tls": [settings.creds_partition_name],
             "network": [settings.app_nvs_partition_name],
             "all": [settings.app_nvs_partition_name, settings.creds_partition_name]}[target]
    with tempfile.TemporaryDirectory(prefix="mmca-erase-") as temporary:
        table_file = Path(temporary) / "partition-table.bin"
        _run_esptool(port, "read-flash", hex(PARTITION_TABLE_OFFSET),
                     hex(PARTITION_TABLE_READ_SIZE), str(table_file))
        table_data = table_file.read_bytes()
        partitions = [_lookup_nvs_partition(table_data, name) for name in names]
        for partition in partitions:
            if partition.offset + partition.size > flash_size:
                raise SafetyError(f"{partition.name} partition extends beyond the detected flash size")
        if len(partitions) == 2:
            first, second = partitions
            if (first.offset < second.offset + second.size and
                    second.offset < first.offset + first.size):
                raise SafetyError("Partitions selected for erasure overlap; refusing to erase")

        for partition in partitions:
            output_fn(f"Will erase the `{partition.name}` partition at 0x{partition.offset:X} "
                      f"({partition.size} bytes) on {port}.")
        if target == "tls":
            output_fn("Wi-Fi, MQTT broker settings, and BLE bonds in the application NVS partition "
                      "will be left untouched.")
        elif target == "network":
            output_fn("This clears the Wi-Fi SSID and password, MQTT broker host and port, "
                      "Wi-Fi driver state, and BLE bonds.")
            output_fn("TLS credentials in the separate creds partition will be left untouched.")
        else:
            output_fn("This clears TLS credentials, Wi-Fi and MQTT broker settings, and BLE bonds.")
        phrase = ESP_ERASE_PHRASES[target]
        if input_fn(f"Type {phrase} to continue: ").strip() != phrase:
            raise MMCAError("ESP erasure cancelled")

        # Keep the chip in the bootloader between erase and read-back: if the
        # firmware booted, nvs_flash_init() would write page headers into the
        # blank partitions. Only the final read-back resets into the firmware.
        for partition in partitions:
            _run_esptool(port, "erase-region", hex(partition.offset), hex(partition.size),
                         after="no-reset")
        for index, partition in enumerate(partitions):
            readback = Path(temporary) / f"erase-readback-{index}.bin"
            last = index == len(partitions) - 1
            _run_esptool(port, "read-flash", hex(partition.offset), hex(partition.size),
                         str(readback), after=None if last else "no-reset")
            if readback.read_bytes() != b"\xff" * partition.size:
                raise SafetyError(f"ESP {partition.name} erase verification failed")

    erased_at = datetime.now(timezone.utc).isoformat()
    if target in ("tls", "all"):
        meta["credentials_erased"] = True
        meta["credentials_erased_at"] = erased_at
    if target in ("network", "all"):
        meta["network_erased"] = True
        meta["network_erased_at"] = erased_at
    (directory / "meta.json").write_text(json.dumps(meta, sort_keys=True, indent=2) + "\n",
                                        encoding="utf-8")
    os.chmod(directory / "meta.json", 0o600)
    regions = [{"name": p.name, "offset": f"0x{p.offset:X}", "size": p.size} for p in partitions]
    append_event(settings.audit_path, "erase_esp", device_id=device_id,
                 details={"target": target, "port": port, "chip_mac": chip_mac,
                          "partitions": regions})
    return {"port": port, "chip_mac": chip_mac, "target": target,
            "partitions": [{"name": p.name, "offset": p.offset, "size": p.size}
                           for p in partitions]}


def erase_esp(settings: Settings, device_id: str, requested_port: str | None = None,
              *, target: str, input_fn=input, output_fn=print, ports_fn=list_ports) -> dict:
    try:
        return _erase_esp(settings, device_id, requested_port, target, input_fn=input_fn,
                          output_fn=output_fn, ports_fn=ports_fn)
    except Exception as exc:
        try:
            canonical_id = validate_device_id(device_id)
            append_event(settings.audit_path, "erase_esp", device_id=canonical_id,
                         result="failed", details={"target": target,
                                                   "reason": type(exc).__name__})
        except Exception:
            pass
        raise


def erase_esp_credentials(settings: Settings, device_id: str,
                          requested_port: str | None = None, *, input_fn=input,
                          output_fn=print, ports_fn=list_ports) -> dict:
    return erase_esp(settings, device_id, requested_port, target="tls", input_fn=input_fn,
                     output_fn=output_fn, ports_fn=ports_fn)
