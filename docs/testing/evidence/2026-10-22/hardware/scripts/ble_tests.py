"""BLE provisioning tests from the laptop (TC-P09, TC-P10, TC-P12). Appends records to a JSON log.

Usage: ble_tests.py <pair|invalid|wrong-wifi|restore|drop|write-unpaired> <record.json>
The hotspot password is read from hotspot_psk next to this script and never written to the record.
"""
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from bleak import BleakClient

HERE = Path(__file__).resolve().parent
NAME = "MM-GW-DA7EEC"
CHAR = "7a2e0002-2b3c-4d5e-8f90-123456789abc"
SSID, HOST, PORT = "f-gateway-AP", "10.42.0.1", 8883
PSK = (HERE / "hotspot_psk").read_text().strip()

INVALID = [
    ("empty SSID", {"ssid": "", "password": "12345678", "broker_host": HOST, "broker_port": PORT}),
    ("password too short", {"ssid": "x", "password": "short", "broker_host": HOST, "broker_port": PORT}),
    ("bad broker host", {"ssid": "x", "password": "12345678", "broker_host": "bad host!", "broker_port": PORT}),
    ("port out of range", {"ssid": "x", "password": "12345678", "broker_host": HOST, "broker_port": 70000}),
    ("missing fields", {"ssid": "x"}),
    ("not JSON", "not json"),
]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def encode(payload):
    return (payload if isinstance(payload, str) else json.dumps(payload)).encode()


def shown(payload):
    if isinstance(payload, dict) and payload.get("password") == PSK:
        return {**payload, "password": "<hotspot password>"}
    return payload


ADDRESS = "B8:1F:3F:DA:7E:EE"


async def connect():
    client = BleakClient(ADDRESS, timeout=30)
    await client.connect()
    return client


async def write(client, payload):
    start = time.time()
    try:
        await asyncio.wait_for(client.write_gatt_char(CHAR, encode(payload), response=True), 20)
        result = {"accepted": True}
    except Exception as exc:
        result = {"accepted": False, "error": f"{type(exc).__name__}: {exc}"}
    result["seconds"] = round(time.time() - start, 2)
    return result


def bluez_paired():
    import subprocess
    info = subprocess.run(["bluetoothctl", "info", ADDRESS], capture_output=True, text=True).stdout
    return "Paired: yes" in info


async def main(modes, out):
    client = await connect()
    records = json.loads(Path(out).read_text()) if Path(out).exists() else []
    print("connected", flush=True)
    try:
        for mode in modes.split(","):
            steps = [{"step": "connected", "at": now()}]
            await run_mode(client, mode, steps)
            records.append({"mode": mode, "steps": steps})
            Path(out).write_text(json.dumps(records, indent=2))
            print(json.dumps({"mode": mode, "steps": steps}, indent=2), flush=True)
    finally:
        if client.is_connected:
            await client.disconnect()


async def run_mode(client, mode, steps):
    if mode.startswith("wait:"):
        await asyncio.sleep(int(mode[5:]))
        steps.append({"step": f"waited {mode[5:]} s", "at": now()})
        return
    if True:
        if mode in ("pair", "write-unpaired"):
            start = time.time()
            try:
                await asyncio.wait_for(client.pair(), 60)
                outcome = {}
            except Exception as exc:
                outcome = {"error": f"{type(exc).__name__}: {exc}"}
            outcome["paired_per_bluez"] = bluez_paired()
            outcome["seconds"] = round(time.time() - start, 1)
            steps.append({"step": "pair (passkey typed by the tester)", "at": now(), **outcome})
            if mode == "write-unpaired":
                probe = {"ssid": "P12-WRONG-PASSKEY", "password": "12345678",
                         "broker_host": HOST, "broker_port": PORT}
                steps.append({"step": "write after failed pairing", "at": now(),
                              "payload": probe, **await write(client, probe)})
        elif mode == "invalid":
            for label, payload in INVALID:
                steps.append({"step": f"invalid: {label}", "at": now(), "payload": payload,
                              **await write(client, payload)})
                await asyncio.sleep(1)
        elif mode in ("wrong-wifi", "restore"):
            password = "wrong-password-123" if mode == "wrong-wifi" else PSK
            payload = {"ssid": SSID, "password": password, "broker_host": HOST, "broker_port": PORT}
            steps.append({"step": mode, "at": now(), "payload": shown(payload),
                          **await write(client, payload)})
        elif mode == "drop":
            payload = {"ssid": SSID, "password": PSK, "broker_host": HOST, "broker_port": PORT}
            task = asyncio.create_task(write(client, payload))
            await asyncio.sleep(0)
            await client.disconnect()
            steps.append({"step": "write then immediate disconnect", "at": now(),
                          "payload": shown(payload), **await task})


asyncio.run(main(sys.argv[1], sys.argv[2]))
