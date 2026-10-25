# Dashboard system admin screens (dashboard Phase 4)

- **Date:** 2026-10-26
- **Type:** code
- **Module:** M8 dashboard
- **Commits:** see `git log -- web/dashboard/` on `feat/dashboard`

## What changed
- **Dashboard:** organisation and device counts by status, the latest security events and registry changes.
- **Organisations:**
  - list and create (public or private);
  - an organisation's page: suspend or reactivate (the confirmation says that every member is refused while it is suspended, as `auth.get_principal` does);
  - create an organisation administrator, with the **invite code shown once** until the admin confirms they passed it on;
  - the administrators created (from the registry audit log, since no endpoint lists them to the system admin);
  - the devices granted to it (read from each device's grants, since there is no grants-by-organisation endpoint).
- **Devices:**
  - list with filters (id, type, status, testbed);
  - register by the UUID the certificate was issued for (validated);
  - a device's page: facts and liveness; lifecycle (activate only with an active credential; suspend; revoke with its cascade spelled out);
  - certificates: add by SHA-256 fingerprint (colons and lower case accepted, validated), revoke;
  - the organisation grant: grant to an active organisation, end it, history.
- **Security events:** filter by mode, predicted class and outcome; a detail panel; links to the gateway and device.
- **Audit log:** registry changes with target links, organisation names, "You" for the signed-in admin, and readable details.
- **Attack tests:**
  - in API mode, "not available yet" (Iteration 5);
  - in sample mode, start and stop against testbed devices (production refused, one run per device), with results that compare each window with the IDS events: events in the window, first detection after N s, or a missed detection.
  - Shaped on `stack.md` ("Attack-testing"): `{attack_type, target_device_id, params}`.
- **Account page** for all four roles: name (from the directory), role, organisation, id, sign-out, and where the password is changed.
- **Shared pieces for the later phases:**
  - `useResource` (load and reload, keeping data on screen while refreshing) and `useAction` (busy state and an outcome notice);
  - table, form, notice, confirm dialog, one-time code, record id, metric, page state and unavailable components;
  - labels for the API's codes;
  - messages for the API's constraint conflicts (names checked against the live database).
- **Sample data:**
  - members of a suspended organisation are refused;
  - a duplicate certificate fingerprint is refused;
  - the real constraint names are used;
  - the org admin accounts appear in the audit log;
  - ids differ in the block screens show.
- **Fixes found while building:**
  - Phones zoomed out on pages with tables. Screen-reader text inside a table escaped its scrolling box and widened the page. The table box is now `relative`.
  - The browser tests' overflow check compared against the widened viewport, so it could not catch this. It now compares against the device width.
  - Confirm dialogs with the same label shared one element id.
- **Invite help page:** checked against ZITADEL v4.20 (see Evidence); it now mentions the passkey option.

## Why
Phase 4 of the dashboard rebuild: the system administrator's screens over the registry endpoints (D9 rows for organisations, devices, credentials, grants, security events, audit).

## Evidence
`docs/testing/evidence/2026-10-26/dashboard-phase-4/`:
- `checks.txt`: typecheck, lint, 79 unit tests, production build.
- `e2e-mock.txt`: 30 browser tests, desktop and phone. The system admin flows:
  - organisation and administrator, with the invite code gone after confirmation;
  - device registration, certificate, activation, grant, and the revoke confirmation;
  - an attack test run;
  - security event detail;
  - every system page fits a phone screen.
- `e2e-api.txt`: 7 browser tests against a real cloud stack. The new one:
  - creates an organisation and its administrator;
  - registers a device, adds a certificate, activates and grants it;
  - checks the audit log and the unavailable attack tests;
  - then the new administrator **redeems the invite code in ZITADEL's login** (e-mail, code, choose password) and lands on the organisation dashboard.

## Review
`/code-review high` found ten issues (`docs/testing/review-findings/2026-10-26-dashboard-phase-4-system-admin-screens.md`); nine are fixed in a follow-up commit:
- the one-time invite code can no longer be lost to a failed reload or a silent copy failure;
- attack-test windows older than the loaded events are "not covered" rather than "missed";
- the rate is required;
- "Loaded" shows the fetch time;
- smaller fixes.

The per-device grants requests stay until the cloud offers grants by organisation.
