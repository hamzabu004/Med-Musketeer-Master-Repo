"""TC-W08 and TC-W09: the on-device model's beat pipeline (main/ecg_beats.c) and alert rule
(main/edge_rule.c), built on the host with gcc. Run with:

    python -m pytest firmware/wearable/tools/test_ecg_beats.py

The synthetic tests need only gcc. The MIT-BIH tests also need numpy and scipy and the database
(MM_MITDB_DIR, see mitdb.py); the classification test also needs ai_edge_litert. Without them
those tests are skipped.
"""
import math
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
WEARABLE = TOOLS.parent
MAIN = WEARABLE / "main"
sys.path.insert(0, str(TOOLS))

FS_IN, FS, CPM = 500, 128, 200
LEARN_S = 2.5  # filters settling plus threshold learning, after start or leads off

# alert.c's and ecg_synth.c's beat: Gaussian waves (mV, centre s, width s) from the beat's start.
WAVES = [(0.15, 0.20, 0.025), (-0.10, 0.33, 0.010), (1.20, 0.36, 0.012), (-0.25, 0.39, 0.012),
         (0.30, 0.60, 0.040)]
R_OFFSET = 0.36


def ecg_mv(t: float, onsets: list[float]) -> float:
    """The synthetic trace at time t, for beats starting at the given onsets."""
    v = 0.0
    for o in onsets:
        dt = t - o
        if -0.1 < dt < 1.0:
            v += sum(a * math.exp(-0.5 * ((dt - c) / w) ** 2) for a, c, w in WAVES)
    return v


def onsets_at(rr: list[float], start: float = 0.0) -> list[float]:
    out, t = [], start
    for r in rr:
        out.append(t)
        t += r
    return out


def samples(onsets: list[float], seconds: float, off: tuple[float, float] | None = None) -> bytes:
    """500 Hz records for the host program: int16 counts and one leads-off byte."""
    out = bytearray()
    for i in range(int(seconds * FS_IN)):
        t = i / FS_IN
        lo = 1 if off and off[0] <= t < off[1] else 0
        c = 0 if lo else max(-32768, min(32767, round(ecg_mv(t, onsets) * CPM)))
        out += struct.pack("<hB", c, lo)
    return bytes(out)


@pytest.fixture(scope="module")
def beats_bin(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("needs gcc")
    binary = tmp_path_factory.mktemp("beats") / "ecg_beats"
    subprocess.run(["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", f"-I{MAIN}",
                    str(TOOLS / "host_stubs" / "ecg_beats_main.c"), str(MAIN / "ecg_beats.c"), "-lm",
                    "-o", str(binary)], check=True)
    return binary


def run_beats(binary: Path, data: bytes) -> list[dict]:
    out = subprocess.run([str(binary)], input=data, capture_output=True, check=True).stdout.decode()
    beats = []
    for line in out.splitlines():
        v = line.split()
        beats.append({"r": int(v[0]), "pre_rr_s": float(v[1]), "rr": [float(x) for x in v[2:6]],
                      "win": [float(x) for x in v[6:70]]})
    return beats


def test_tc_w08_finds_every_beat_at_its_r_peak(beats_bin):
    onsets = onsets_at([60 / 72] * 80)
    beats = run_beats(beats_bin, samples(onsets, 60))
    true_r = [o + R_OFFSET for o in onsets if LEARN_S + 0.3 < o + R_OFFSET < 59]
    found = [b["r"] / FS for b in beats]
    # Every beat after learning, except the last (it waits for the next R peak), within 1 sample.
    for t in true_r[:-1]:
        assert min(abs(f - t) for f in found) <= 1 / FS + 1e-9, t
    assert len(found) <= len(true_r) + 1


def test_tc_w08_window_is_the_signal_at_128_hz(beats_bin):
    # The resampler has no delay: window sample i is the trace at (r - 32 + i) / 128 s.
    onsets = onsets_at([0.8] * 30)
    beats = run_beats(beats_bin, samples(onsets, 20))
    assert beats
    for b in beats:
        expected = [ecg_mv((b["r"] - 32 + i) / FS, onsets) for i in range(64)]
        assert max(abs(w - e) for w, e in zip(b["win"], expected)) < 0.03
        assert max(range(64), key=lambda i: b["win"][i]) == 32


def test_tc_w08_rr_features(beats_bin):
    # A changing rhythm; check the features against the definition, from the found R peaks.
    rr = [0.8] * 15 + [0.5, 1.1] * 10 + [0.7] * 10
    onsets = onsets_at(rr)
    beats = run_beats(beats_bin, samples(onsets, sum(rr) + 1))
    assert len(beats) > 30
    rs = [b["r"] for b in beats]
    history = []
    for i, b in enumerate(beats[:-1]):
        post = rs[i + 1] - rs[i]
        pre = post if i == 0 else rs[i] - rs[i - 1]
        history.append(pre)
        local = sum(history[-80:]) / len(history[-80:])
        glob = sum(history[-400:]) / len(history[-400:])
        want = [pre / local, pre / glob, post / local, post / glob]
        assert b["rr"] == pytest.approx(want, rel=1e-4), i
        assert b["pre_rr_s"] == pytest.approx(pre / FS, rel=1e-4)


def test_tc_w08_leads_off_resets_and_detection_resumes(beats_bin):
    onsets = onsets_at([0.8] * 50)
    off = (15.0, 17.0)
    beats = run_beats(beats_bin, samples(onsets, 38, off=off))
    found = [b["r"] / FS for b in beats]
    # No beat from the electrodes coming off until learning has finished again.
    assert not [t for t in found if off[0] - 0.5 < t < off[1] + LEARN_S]
    assert [t for t in found if t > off[1] + LEARN_S + 1]
    # The first beat after the gap starts a new RR history (pre = post).
    after = next(b for b in beats if b["r"] / FS > off[1])
    assert after["rr"][0] == pytest.approx(after["rr"][2], rel=1e-6)


def test_tc_w08_flat_signal_gives_no_beats(beats_bin):
    assert run_beats(beats_bin, samples([], 20)) == []


# ---- MIT-BIH: detection against the annotations, and the model on the detected beats ----

def mitdb_records():
    np = pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    from scipy.signal import resample_poly
    import mitdb
    path = mitdb.mitdb_dir()
    if not path:
        pytest.skip("set MM_MITDB_DIR to the MIT-BIH Arrhythmia Database")
    for r in mitdb.DS2:
        x, fs, gain = mitdb.read_signal(path, r)
        y = resample_poly(x.astype(float), 25, 18) * CPM / gain  # 360 -> 500 Hz, as the ADS1292
        rec = np.zeros(len(y), dtype=[("v", "<i2"), ("o", "u1")])
        rec["v"] = np.clip(np.round(y), -32768, 32767)
        t, codes = mitdb.read_annotations(path, r)
        keep = np.isin(codes, list(mitdb.BEAT_CODES))
        yield r, rec.tobytes(), t[keep] / fs, codes[keep], len(x) / fs


def match(found, truth, tol=0.15):
    """Pairs of (found index, truth index) within tol seconds, each used once."""
    import numpy as np
    pairs, used = [], set()
    j = np.searchsorted(found, truth)
    for k, t in enumerate(truth):
        cands = [i for i in (j[k] - 1, j[k]) if 0 <= i < len(found) and i not in used
                 and abs(found[i] - t) <= tol]
        if cands:
            i = min(cands, key=lambda i: abs(found[i] - t))
            used.add(i)
            pairs.append((i, k))
    return pairs


def test_tc_w08_mitdb_detection(beats_bin):
    np = pytest.importorskip("numpy")
    tp = fn = fp = 0
    errors = []
    for _, data, truth_t, _, length in mitdb_records():
        beats = run_beats(beats_bin, data)
        found = np.array([b["r"] / FS for b in beats])
        truth = truth_t[(truth_t > 3.0) & (truth_t < length - 2)]
        found = found[found > 3.0]
        pairs = match(found, truth)
        tp += len(pairs)
        fn += len(truth) - len(pairs)
        fp += len(found) - len(pairs)
        errors += [found[i] - truth[k] for i, k in pairs]
    se, ppv = tp / (tp + fn), tp / (tp + fp)
    within = np.mean(np.abs(np.array(errors)) <= 1 / FS)
    print(f"DS2 detection: Se {100 * se:.2f} %, PPV {100 * ppv:.2f} %, R within one 128 Hz sample "
          f"{100 * within:.1f} %")
    assert se >= 0.995 and ppv >= 0.995
    assert within >= 0.95


def test_tc_w08_mitdb_classification(beats_bin):
    """The deployed INT8 model on beats found by the firmware's pipeline, quantised as
    ecg_classifier.cpp does, against the export's own DS2 result (97.34 % accuracy, macro-F1
    89.45 % with annotated R peaks)."""
    np = pytest.importorskip("numpy")
    litert = pytest.importorskip("ai_edge_litert.interpreter")
    interp = litert.Interpreter(model_path=str(WEARABLE / "model" / "p1_best_int8.tflite"))
    interp.allocate_tensors()
    ins = interp.get_input_details()
    ecg_in = next(d for d in ins if list(d["shape"]) == [1, 64, 1])
    rr_in = next(d for d in ins if list(d["shape"]) == [1, 4])
    out = interp.get_output_details()[0]
    meta = (MAIN / "ecg_model" / "p1_best_model_meta.h").read_text()

    def const(name):
        return float(next(l.split()[2].rstrip("f") for l in meta.splitlines()
                          if l.startswith(f"#define {name} ")))

    def q(x, scale, zp):
        return np.clip(np.round(x / scale) + zp, -128, 127).astype(np.int8)

    import mitdb
    index = {"N": 0, "S": 1, "V": 2}
    cm = np.zeros((3, 3), int)
    for _, data, truth_t, truth_c, _ in mitdb_records():
        beats = run_beats(beats_bin, data)
        found = np.array([b["r"] / FS for b in beats])
        for i, k in match(found, truth_t):
            cls = mitdb.AAMI[int(truth_c[k])]
            if cls not in index:
                continue
            w = np.array(beats[i]["win"])
            sd = w.std() if w.std() > 1e-9 else 1.0
            d = np.diff(w) / sd
            d = np.append(d, d[-1])
            interp.set_tensor(ecg_in["index"], q(d, const("P1_BEST_IN_ECG_SCALE"),
                                                 const("P1_BEST_IN_ECG_ZP")).reshape(1, 64, 1))
            interp.set_tensor(rr_in["index"], q(np.array(beats[i]["rr"]), const("P1_BEST_IN_RR_SCALE"),
                                                const("P1_BEST_IN_RR_ZP")).reshape(1, 4))
            interp.invoke()
            cm[index[cls], int(np.argmax(interp.get_tensor(out["index"])[0]))] += 1
    se = np.diag(cm) / cm.sum(1)
    ppv = np.diag(cm) / np.maximum(cm.sum(0), 1)
    f1 = 2 * se * ppv / np.maximum(se + ppv, 1e-9)
    acc = np.trace(cm) / cm.sum()
    print(f"DS2 on device pipeline: {cm.sum()} beats, accuracy {100 * acc:.2f} %, macro-F1 "
          f"{100 * f1.mean():.2f} %, Se N/S/V {100 * se[0]:.2f}/{100 * se[1]:.2f}/{100 * se[2]:.2f} %, "
          f"PPV S/V {100 * ppv[1]:.2f}/{100 * ppv[2]:.2f} %\n{cm}")
    assert acc >= 0.97 and f1.mean() >= 0.885


# ---- TC-W09: the alert rule ----

@pytest.fixture(scope="module")
def rule_bin(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("needs gcc")
    binary = tmp_path_factory.mktemp("rule") / "edge_rule"
    subprocess.run(["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", f"-I{MAIN}",
                    str(TOOLS / "host_stubs" / "edge_rule_main.c"), str(MAIN / "edge_rule.c"),
                    "-o", str(binary)], check=True)
    return binary


P = {0: "0.9 0.05 0.05", 1: "0.1 0.8 0.1", 2: "0.1 0.1 0.8"}


def rule(binary, beats, window=10, min_abnormal=3, cooldown_ms=60000):
    lines = [b if b == "clear" else f"{b[0]} {P[b[0]]} {b[1]}" for b in beats]
    out = subprocess.run([str(binary), str(window), str(min_abnormal), str(cooldown_ms)],
                         input="\n".join(lines) + "\n", capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def test_tc_w09_three_of_ten_raises_one_alert(rule_bin):
    beats = [(0, t * 800) for t in range(10)] + [(2, 8000), (0, 8800), (2, 9600), (0, 10400), (2, 11200)]
    out = rule(rule_bin, beats)
    assert out[:14] == ["-"] * 14
    assert out[14] == "A V 0.800 3"


def test_tc_w09_two_of_ten_is_not_enough(rule_bin):
    beats = [(2 if i in (3, 7) else 0, i * 800) for i in range(30)]
    assert set(rule(rule_bin, beats)) == {"-"}


def test_tc_w09_abnormal_beats_age_out_of_the_window(rule_bin):
    # S, S, then 9 normal beats, then S: only 2 within any 10 beats.
    beats = [(1, 0), (1, 800)] + [(0, 800 * i) for i in range(2, 11)] + [(1, 9600)]
    assert set(rule(rule_bin, beats)) == {"-"}


def test_tc_w09_cooldown(rule_bin):
    beats = [(2, i * 500) for i in range(200)]  # 100 s of V beats
    out = rule(rule_bin, beats)
    alerts = [i for i, line in enumerate(out) if line.startswith("A")]
    assert alerts == [2, 122]  # the third beat, then 60 s later


def test_tc_w09_label_is_the_more_frequent_class(rule_bin):
    assert rule(rule_bin, [(1, 0), (1, 1), (2, 2)])[-1] == "A S 0.800 3"
    assert rule(rule_bin, [(1, 0), (2, 1), (1, 2), (2, 3)], min_abnormal=4)[-1] == "A V 0.800 4"


def test_tc_w09_clear_forgets_the_window(rule_bin):
    assert rule(rule_bin, [(2, 0), (2, 1), "clear", (2, 2), (2, 3)]) == ["-"] * 5
