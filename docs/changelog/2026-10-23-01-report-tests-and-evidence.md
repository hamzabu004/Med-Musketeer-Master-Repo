# Report test cases, broker interop tests, and evidence committed

- **Date:** 2026-10-23
- **Type:** test
- **Module:** M1 CA tool, M5 gateway
- **Commits:** 8ec693c

## What changed
- Added `test_report_cases.py` (TC-P01, TC-P02, TC-A01 to TC-A06, TC-A09), `test_repo_hygiene.py` (TC-P11 secret scan) and `test_broker_interop.py` (TC-B01 to TC-B04 on a Mosquitto container) to `tools/ca-tool/tests/`, and `run_report_tests.sh` to regenerate the evidence.
- Committed `docs/testing/`: the traceability table, the hardware test procedures, and the 2026-10-22 evidence run.
- `pyproject.toml`: added `pytest-cov` and the `interop` marker.
- The audit-log case is numbered TC-A09 in the docs (previously TC-A10); the test function keeps its old name so it matches the recorded evidence.

## Why
The tests and evidence existed only locally, so GitHub showed 25 tests in 5 files instead of 56.

## Evidence
56 tests pass (re-run 2026-10-23, including broker interop). Evidence in `docs/testing/evidence/2026-10-22/`.
