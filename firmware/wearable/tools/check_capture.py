"""Checks a wearable's alert and status messages against the cloud's own contracts (H-W01, H-W02).

Input is a capture in `mosquitto_sub -v` form, one `<topic> <payload>` per line, for example from
the gateway's services listener:

    mosquitto_sub -h 127.0.0.1 -u gw_services -P "$PI_GW_SERVICES_PASS" -v -t 'mm/fixed/+/#' > capture.txt
    cloud/backend/.venv/bin/python firmware/wearable/tools/check_capture.py capture.txt --device-id <uuid>

The payloads are validated with alert-payload-v1 and status-v1 from cloud/backend/app/contracts.py,
so the check is the one ingestion applies. On top of that, per device: seq goes up, no msg_id
repeats, and segment_start is not later than sent_at. Exits 1 if any line fails.
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "cloud" / "backend"))
from app.contracts import AlertPayload, StatusPayload  # noqa: E402
from pydantic import ValidationError  # noqa: E402

CONTRACTS = {"alert": AlertPayload, "status": StatusPayload}


@dataclass
class Report:
    counts: dict[str, int] = field(default_factory=lambda: {"alert": 0, "status": 0})
    errors: list[str] = field(default_factory=list)


def check(lines: list[str], device_id: str | None = None) -> Report:
    report = Report()
    last_seq: dict[str, int] = {}
    seen_ids: set[tuple[str, str]] = set()
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        def fail(reason: str) -> None:
            report.errors.append(f"line {number}: {reason}")

        topic, _, raw = line.partition(" ")
        parts = topic.split("/")
        if len(parts) != 4 or parts[:2] != ["mm", "fixed"] or parts[3] not in CONTRACTS:
            fail(f"unexpected topic {topic!r}")
            continue
        sender, msg_type = parts[2], parts[3]
        if device_id and sender != device_id:
            fail(f"topic names {sender}, expected {device_id}")
        try:
            payload = CONTRACTS[msg_type].model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as error:
            fail(f"{msg_type} is not valid: {error}".replace("\n", "; "))
            continue
        report.counts[msg_type] += 1
        if msg_type == "status":
            if payload.revocation_version is not None:
                fail("a wearable's status must not carry revocation_version (D16)")
            continue

        if (sender, str(payload.msg_id)) in seen_ids:
            fail(f"msg_id {payload.msg_id} repeats")
        seen_ids.add((sender, str(payload.msg_id)))
        # seq restarts at 0 when the wearable reboots, so only a step other than +1 is reported.
        previous = last_seq.get(sender)
        if previous is not None and payload.seq not in (previous + 1, 0):
            fail(f"seq {payload.seq} follows {previous}")
        last_seq[sender] = payload.seq
        if payload.sent_at and payload.segment_start > payload.sent_at:
            fail("segment_start is later than sent_at")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", type=Path)
    parser.add_argument("--device-id", help="the wearable's id (its certificate CN)")
    args = parser.parse_args()
    report = check(args.capture.read_text().splitlines(), args.device_id)
    for error in report.errors:
        print(error)
    print(f"alerts: {report.counts['alert']}, status: {report.counts['status']}, errors: {len(report.errors)}")
    return 1 if report.errors or not any(report.counts.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
