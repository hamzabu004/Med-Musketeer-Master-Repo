# TC-B05 waits for Mosquitto's reload before checking that the wearable is cut off

- **Date:** 2026-10-30
- **Type:** test
- **Module:** M5 gateway
- **Commits:** see `git log -- gateway/uplink/tests/test_interop.py`

## What changed
`test_tc_b05_*` now waits for the broker's "Reloading config" log line after the uplink applies the list, before sending the listed wearable's next message. The recorded `list_to_enforced_and_reported_s` now runs until the broker has reloaded, and must stay under 10 s.

## Why
The uplink counts a list as enforced once it has rewritten the ACL file and sent SIGHUP; Mosquitto reloads a moment later. On a slow CI runner the wearable's message arrived before the reload and was delivered, so the test failed once on PR #8 (Gateway uplink run 40960601380, passed on re-run). The uplink's behaviour is unchanged; only the test's timing was wrong. The same ordering applies to the Pi run (H-B06 step 2 already checks the journal for "Reloading config").

## Evidence
`tests/test_interop.py` run three times locally against the container brokers: 4 passed each time.
