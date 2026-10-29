# Revocation sync, Slice 3: the dashboard flags stale gateways, and the gateway clock is set up (Iteration 4)

- **Date:** 2026-10-30
- **Type:** code
- **Module:** M8 dashboard, M5 gateway
- **Commits:** see `git log -- web/dashboard gateway/uplink tools/Fixed-Gateway-Setup/setup_uplink.sh`

## What changed
- **Dashboard (system admin):**
  - The devices list has a "Revocation list" column for active gateways: current, behind, or not reported.
  - The device page shows the same state, plus "Status since". Its confirm texts now say what the broker does: a gateway is disconnected at once; a wearable is refused by every gateway through the list; a single revoked wearable certificate stops at the gateway only once the wearable is suspended.
  - The system dashboard has a "Gateways behind the revocation list" metric.
  - All three read `GET /admin/revocation` (`registry.revocation()`), with the API's stale rule (`features/system/revocation-list.ts`).
  - The API types are regenerated from the current API.
- **Sample mode:**
  - It raises the list version on the same changes as the API.
  - A second gateway (Northside) reports an older version, so the flag shows.
  - A world stored in `sessionStorage` by an older build is replaced instead of breaking the new screens.
- **Gateway clock:**
  - `setup_uplink.sh` installs `fake-hwclock`, reminds about the Pi 5 RTC battery, and reports the NTP state.
  - The uplink logs at start whether the clock has been synchronised since boot (`clock_synchronised()`); the backlog will reuse that check.
- **Moved, not built** (decided 2026-10-30): the backlog quarantine and TC-C32. The backlog payload does not exist yet, so the quarantine rule is recorded as a requirement on the backlog design (`gaps.md`, D16): data a revoked wearable sent before `status_changed_at` is stored, data sent after it is quarantined, and its timestamp is trusted only with the clock-synchronised flag.
- **Docs:** `iteration-4-revocation-sync.md` (Slice 3 as done), `iteration-6-dashboard.md` (system admin screens), `stack.md`, `cloud-backend.md` D16, `gaps.md`, `test_traceability.md` (TC-D13), `hardware_test_procedures.md` (H-B06 clock check).

## Why
Exit criterion 4 of the plan: the system admin sees each gateway's list version, and stale gateways are flagged. The clock set-up keeps certificate checks and future backlog timestamps sane after an offline reboot. The quarantine cannot be built before there is a backlog to quarantine.

## Evidence
`docs/testing/evidence/2026-10-30/dashboard-revocation/`:
- `checks.txt`: typecheck, lint, and 101 unit tests pass.
- `e2e-mock.txt`: 50 sample-mode browser tests pass, desktop and phone, including the new stale-gateway test and every page fitting a phone screen.
- `uplink-unit.txt`: 17 uplink unit tests pass, including the clock check.

The API-mode browser tests were not run; they need the ZITADEL stack.
