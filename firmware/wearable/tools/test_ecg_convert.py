"""TC-W07: the ADS1292 conversion in main/ecg_convert.c, built on the host with gcc.

Frame parsing (status header, 24-bit sign extension, channel 1 lead-off bits), codes to microvolts
at the internal 2.42 V reference and gain 6, the DC blocker, microvolts to int16 counts at
200 counts/mV with rounding and clamping, and the leads-off count. Run with:

    python -m pytest firmware/wearable/tools/test_ecg_convert.py
"""
import math
import shutil
import subprocess
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
MAIN = TOOLS.parent / "main"

VREF_UV, GAIN, COUNTS_PER_MV = 2_420_000, 6, 200
LSB_UV = 2 * VREF_UV / GAIN / 2**24  # about 0.0481 uV


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("needs gcc")
    binary = tmp_path_factory.mktemp("ecg") / "ecg_convert"
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", f"-I{MAIN}",
                    str(TOOLS / "host_stubs" / "ecg_convert_main.c"), str(MAIN / "ecg_convert.c"),
                    "-lm", "-o", str(binary)], check=True)

    def call(*commands: str) -> list[list[str]]:
        out = subprocess.run([str(binary)], input="\n".join(commands) + "\n", check=True,
                             capture_output=True, text=True).stdout
        return [line.split() for line in out.splitlines()]
    return call


def frame(status: int, ch1: int, ch2: int = 0) -> str:
    return "frame " + "".join(f"{v & 0xFFFFFF:06x}" for v in (status, ch1, ch2))


def test_tc_w07_parses_a_frame(run):
    assert run(frame(0xC00000, 0x123456, -2)) == [["1", "c00000", str(0x123456), "-2", "0"]]


def test_tc_w07_sign_extends_24_bit_codes(run):
    (r,) = run(frame(0xC00000, 0x800000, 0x7FFFFF))
    assert (int(r[2]), int(r[3])) == (-(2**23), 2**23 - 1)


def test_tc_w07_refuses_a_frame_without_the_status_header(run):
    # Read out of step with DRDY, or MISO stuck: the first nibble is not 1100.
    assert run(frame(0x000000, 5), frame(0xFFFFFF, 5))[0][0] == "0"
    assert run(frame(0xFFFFFF, 5))[0][0] == "0"


@pytest.mark.parametrize("status, off", [
    (0xC00000, "0"),
    (0xC00000 | 1 << 15, "1"),  # IN1P off
    (0xC00000 | 1 << 16, "1"),  # IN1N off
    (0xC00000 | 1 << 17 | 1 << 18 | 1 << 19, "0"),  # channel 2 and RLD do not count
])
def test_tc_w07_channel_1_leads_off(run, status, off):
    assert run(frame(status, 0))[0][4] == off


def test_tc_w07_codes_to_microvolts(run):
    (r,) = run("uv 0 1 -1 8388607 -8388608 20797")
    values = [float(v) for v in r]
    assert values[0] == 0
    assert values[1] == pytest.approx(LSB_UV, rel=1e-4)
    assert values[3] == pytest.approx(VREF_UV / GAIN, rel=1e-4)  # full scale: about 403 mV
    assert values[4] == pytest.approx(-VREF_UV / GAIN, rel=1e-4)
    assert values[5] == pytest.approx(1000, abs=0.1)  # about 1 mV


def test_tc_w07_microvolts_to_counts(run):
    # 5 uV per count; halves round away from zero.
    assert run("counts 200 1000 -1000 5 2.5 -2.5 2.4") == [["200", "-200", "1", "1", "-1", "0"]]


def test_tc_w07_counts_clamp_to_int16(run):
    assert run("counts 200 400000 -400000") == [["32767", "-32768"]]


def test_tc_w07_dc_blocker_removes_the_electrode_offset(run):
    # A 300 mV offset would clamp int16; the first sample primes the filter, so no step remains.
    (r,) = run("hp 0.5 500 " + " ".join(["300000"] * 1000))
    assert all(float(v) == 0 for v in r)


def test_tc_w07_dc_blocker_passes_ecg_frequencies(run):
    fs, f = 500, 10.0
    x = [300000 + 1000 * math.sin(2 * math.pi * f * i / fs) for i in range(3000)]
    (r,) = run("hp 0.5 500 " + " ".join(f"{v:.3f}" for v in x))
    tail = [float(v) for v in r[2000:]]
    amplitude = (max(tail) - min(tail)) / 2
    assert amplitude == pytest.approx(1000, rel=0.01)


def test_tc_w07_dc_blocker_corner(run):
    # At the 0.5 Hz corner a first-order high-pass passes about 1/sqrt(2).
    fs, f = 500, 0.5
    x = [1000 * math.sin(2 * math.pi * f * i / fs) for i in range(20000)]
    (r,) = run("hp 0.5 500 " + " ".join(f"{v:.3f}" for v in x))
    tail = [float(v) for v in r[10000:]]
    assert (max(tail) - min(tail)) / 2 == pytest.approx(1000 / math.sqrt(2), rel=0.03)


def test_tc_w07_counts_leads_off(run):
    assert run("lo 0 1 1 0 2 0", "lo 0 0 0", "lo") == [["3"], ["0"], ["0"]]
