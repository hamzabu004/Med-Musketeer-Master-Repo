"""Atomic file replacement: a reader sees the old file or the new one, never part of one."""
import os
import tempfile
from pathlib import Path


def replace(path: Path, text: str, mode: int = 0o600) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)  # the rename itself survives a power cut
    finally:
        os.close(directory)
