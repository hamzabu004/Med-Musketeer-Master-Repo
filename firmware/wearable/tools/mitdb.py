"""Reads MIT-BIH Arrhythmia Database records (format 212 signals, .atr annotations) with numpy
only, for the host tests of the beat pipeline. The database is not in the repository: set
MM_MITDB_DIR to a directory holding the .hea, .dat and .atr files of the records."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

# Beat annotation codes (wfdb ecgcodes) and their AAMI class.
AAMI = {1: "N", 2: "N", 3: "N", 34: "N", 11: "N",       # N L R e j
        4: "S", 7: "S", 8: "S", 9: "S",                  # a J A S
        5: "V", 10: "V",                                 # V E
        6: "F", 12: "Q", 38: "Q", 13: "Q"}               # F / f Q
BEAT_CODES = set(AAMI)
PACED = {"102", "104", "107", "217"}
DS2 = ["100", "103", "105", "111", "113", "117", "121", "123", "200", "202", "210", "212", "213",
       "214", "219", "221", "222", "228", "231", "232", "233", "234"]


def mitdb_dir() -> Path | None:
    d = os.environ.get("MM_MITDB_DIR")
    return Path(d) if d and Path(d, "100.hea").exists() else None


def read_signal(path: Path, record: str, channel: int = 0) -> tuple[np.ndarray, float, float]:
    """The channel's samples in ADC units, the sampling rate, and the gain (ADC units per mV)."""
    header = (path / f"{record}.hea").read_text().splitlines()
    fs = float(header[0].split()[2])
    sig = header[1 + channel].split()
    gain = float(sig[2].split("(")[0].split("/")[0])
    raw = np.fromfile(path / f"{record}.dat", dtype=np.uint8)
    raw = raw[: len(raw) // 3 * 3].reshape(-1, 3).astype(np.int32)
    s0 = raw[:, 0] | ((raw[:, 1] & 0x0F) << 8)
    s1 = raw[:, 2] | ((raw[:, 1] & 0xF0) << 4)
    s0 = np.where(s0 > 2047, s0 - 4096, s0)
    s1 = np.where(s1 > 2047, s1 - 4096, s1)
    return (s0 if channel == 0 else s1), fs, gain


def read_annotations(path: Path, record: str) -> tuple[np.ndarray, np.ndarray]:
    """Sample indices and codes of every annotation in <record>.atr."""
    data = np.fromfile(path / f"{record}.atr", dtype="<u2")
    t, i, times, codes = 0, 0, [], []
    while i < len(data):
        word = int(data[i]); i += 1
        code, diff = word >> 10, word & 0x3FF
        if code == 0 and diff == 0:
            break
        if code == 59:  # SKIP: a 32-bit interval follows, high word first
            t += (int(data[i]) << 16) | int(data[i + 1]); i += 2
            continue
        if code in (60, 61, 62):  # NUM, SUB, CHN
            continue
        if code == 63:  # AUX: diff bytes follow, padded to a word
            i += (diff + 1) // 2
            continue
        t += diff
        times.append(t); codes.append(code)
    return np.asarray(times), np.asarray(codes)
