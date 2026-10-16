from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_private(path: Path, data: bytes, *, replace: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists() and not replace:
            raise FileExistsError(path)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        temp_path.unlink(missing_ok=True)


def write_public(path: Path, data: bytes, *, replace: bool = False) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise FileExistsError(path)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        os.chmod(path, 0o644)
    finally:
        temp_path.unlink(missing_ok=True)


def write_json_private(path: Path, value: Any) -> None:
    payload = json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    write_private(path, payload, replace=path.exists())
