from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SAFE_DETAIL_KEYS = {"port", "chip_mac", "flash_size", "partition_offset", "partition_size",
                    "host", "files", "reason", "target", "partitions"}


def append_event(path: Path, action: str, *, device_id: str | None = None,
                 fingerprint: str | None = None, result: str = "success",
                 details: dict[str, Any] | None = None) -> None:
    event: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "device_id": device_id,
        "fingerprint": fingerprint,
        "result": result,
    }
    if details:
        event["details"] = {key: value for key, value in details.items() if key in SAFE_DETAIL_KEYS}
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
    except Exception:
        raise


def read_events(path: Path, device_id: str | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result = []
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid audit record on line {line_no}") from exc
            if device_id is None or event.get("device_id") == device_id:
                result.append(event)
    return result
