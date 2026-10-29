"""Test helper: device payloads (shared/contracts) and the ingest-v1 messages the adapter builds."""
import base64
import math
import struct
import uuid
from datetime import UTC, datetime, timedelta

FS_HZ = 360


def ecg_samples(n: int) -> list[int]:
    return [round(200 * math.sin(2 * math.pi * 1.2 * i / FS_HZ)) for i in range(n)]


def encode(samples: list[int]) -> str:
    return base64.b64encode(struct.pack(f"<{len(samples)}h", *samples)).decode()


def alert_payload(n_samples: int = FS_HZ * 3, **overrides) -> dict:
    now = datetime.now(UTC)
    return {
        "v": 1, "msg_id": str(uuid.uuid4()), "seq": 7, "type": "alert", "fs_hz": FS_HZ, "lead": "MLII",
        "n_samples": n_samples, "encoding": "int16le-base64", "samples": encode(ecg_samples(n_samples)),
        "screening": {"label": "abnormal", "confidence": 0.93, "model": "tinydl-0.1"},
        "segment_start": (now - timedelta(seconds=4)).isoformat(), "sent_at": (now - timedelta(seconds=1)).isoformat(),
        **overrides,
    }


def status_payload(state: str = "online", **overrides) -> dict:
    return {"v": 1, "state": state, **overrides}


def ids_payload(**overrides) -> dict:
    return {"v": 1, "msg_id": str(uuid.uuid4()), "ts": datetime.now(UTC).isoformat(), "mode": "ips",
            "predicted_class": "dos_flood", "outcome": "blocked", "action": "drop_source", "action_result": "applied",
            **overrides}


def ingest(device_id, gateway_id, msg_type: str, payload: dict, *, device_type: str = "wearable",
           received_at: datetime | None = None, **overrides) -> dict:
    received_at = received_at or datetime.now(UTC)
    return {
        "device_id": str(device_id), "device_type": device_type, "auth_method": "x509_mtls",
        "attested_by": str(gateway_id) if gateway_id else None, "authenticated": True,
        "auth_metadata": {"listener": "ssl:gateway"}, "msg_type": msg_type, "received_at": received_at.isoformat(),
        "hops": {"sent_at": payload.get("sent_at"), "broker_at": received_at.isoformat(),
                 "adapter_at": (received_at + timedelta(milliseconds=3)).isoformat()},
        "payload": payload, **overrides,
    }
