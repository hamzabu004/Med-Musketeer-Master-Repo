from __future__ import annotations

import asyncio
from typing import Callable

from .audit import append_event
from .config import Settings
from .errors import MMCAError

PROVISIONING_SERVICE_UUID = "7a2e0001-2b3c-4d5e-8f90-123456789abc"
PROVISIONING_CONFIG_UUID = "7a2e0002-2b3c-4d5e-8f90-123456789abc"
WIFI_CLEAR_PHRASE = "CLEAR WIFI CREDENTIALS"


async def _send_clear_wifi(device_name: str, timeout: float = 20.0) -> str:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise MMCAError("BLE support is missing; install the CA Tool dependencies again") from exc

    devices = await BleakScanner.discover(timeout=timeout)
    matches = [device for device in devices if device.name == device_name]
    if not matches:
        raise MMCAError(f"Could not find BLE gateway {device_name!r}; keep it powered and advertising")
    if len(matches) > 1:
        raise MMCAError(f"More than one BLE gateway advertises as {device_name!r}")

    device = matches[0]
    # Pairing uses the operating system's Bluetooth agent; enter the passkey shown
    # on the gateway display if the agent asks for it.
    async with BleakClient(device, pair=True, timeout=30.0) as client:
        if not client.is_connected:
            raise MMCAError("BLE connection to the gateway failed")
        if PROVISIONING_SERVICE_UUID not in {service.uuid.lower() for service in client.services}:
            raise MMCAError("Connected device does not expose the MedMusketeer provisioning service")
        await client.write_gatt_char(
            PROVISIONING_CONFIG_UUID,
            b'{"action":"clear_wifi"}',
            response=True,
        )
    return device.address


def clear_wifi_credentials(settings: Settings, device_name: str, *, device_id: str | None = None,
                           input_fn: Callable[[str], str] = input,
                           output_fn: Callable[[str], None] = print) -> dict[str, str]:
    if not device_name.startswith("MM-GW-"):
        raise MMCAError("--device-name must match the gateway name shown on its display (MM-GW-XXXXXX)")
    output_fn("This removes the saved Wi-Fi SSID and password.")
    output_fn("MQTT broker settings, BLE bonds, and TLS credentials will be kept.")
    output_fn("The gateway must be nearby, powered, and advertising over BLE.")
    if input_fn(f"Type '{WIFI_CLEAR_PHRASE}' to continue: ").strip() != WIFI_CLEAR_PHRASE:
        raise MMCAError("Wi-Fi credential removal cancelled")

    try:
        address = asyncio.run(_send_clear_wifi(device_name))
    except RuntimeError as exc:
        raise MMCAError(f"Cannot start BLE operation: {exc}") from exc
    except MMCAError:
        raise
    except Exception as exc:
        raise MMCAError(f"BLE Wi-Fi clear request failed: {exc}") from exc
    append_event(settings.audit_path, "clear_wifi", device_id=device_id,
                 details={"reason": "gateway BLE request accepted"})
    return {"device_name": device_name, "address": address}
