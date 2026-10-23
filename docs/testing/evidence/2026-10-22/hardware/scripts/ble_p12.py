"""TC-P12 (first half): write provisioning settings without pairing; record the ATT result."""
import asyncio
import json
import sys
import time
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner

NAME = "MM-GW-DA7EEC"
CONFIG_CHAR = "7a2e0002-2b3c-4d5e-8f90-123456789abc"
PAYLOAD = {"ssid": "P12-UNPAIRED-TEST", "password": "unpaired-test-1",
           "broker_host": "10.42.0.1", "broker_port": 8883}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def main(out):
    record = {"case": "p12-unpaired", "started": now(), "device_name": NAME, "steps": []}
    device = await BleakScanner.find_device_by_name(NAME, timeout=15)
    record["steps"].append({"step": "scan", "found": bool(device),
                            "address": device.address if device else None})
    if device:
        async with BleakClient(device, timeout=20) as client:
            record["steps"].append({"step": "connect", "connected": client.is_connected,
                                    "paired_before_write": False, "mtu": client.mtu_size})
            service = client.services.get_characteristic(CONFIG_CHAR)
            record["steps"].append({"step": "characteristic", "found": bool(service),
                                    "properties": service.properties if service else None})
            start = time.time()
            try:
                await client.write_gatt_char(CONFIG_CHAR, json.dumps(PAYLOAD).encode(), response=True)
                outcome = {"accepted": True}
            except Exception as exc:
                outcome = {"accepted": False, "error": f"{type(exc).__name__}: {exc}"}
            outcome["seconds"] = round(time.time() - start, 1)
            record["steps"].append({"step": "write without pairing", **outcome})
    record["finished"] = now()
    with open(out, "w") as stream:
        json.dump(record, stream, indent=2)
    print(json.dumps(record, indent=2))


asyncio.run(main(sys.argv[1]))
