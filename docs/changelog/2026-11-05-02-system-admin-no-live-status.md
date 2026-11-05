# The system admin no longer sees how devices are doing; the org admin sees each gateway's revocation list

- **Date:** 2026-11-05
- **Type:** code | decision
- **Module:** M7 cloud | M8 dashboard
- **Commits:** pending

## What changed
- `cloud-backend.md` D9: the system admin column of "Devices of own organisation: list, live status" is now ✘. The system admin keeps the registry: each device's lifecycle status (pending, active, suspended, revoked) and when it changed, credentials, grants, and the testbed flag. D16 and D17 were updated to match.
- API:
  - `GET /admin/devices[/{id}]` and the lifecycle answers (register, activate, suspend, revoke) no longer return `last_seen`, `current_mode`, `current_gateway_id` or `revocation_version`.
  - `GET /admin/revocation` returns `version`, `published_version` and `published_at`, and no longer returns `stale_gateways`.
  - The org admin's `GET /gateways[/{id}]` has a new `revocation` field (`reported_version`, `published_version`, `current`) that follows the same staleness rule.
- Dashboard, system admin:
  - The devices list lost its Mode, Last seen and Revocation list columns.
  - The device page lost the Mode, Current gateway, Last seen and Revocation list facts.
  - The organisation page lost Last seen.
  - The dashboard's "Gateways behind the revocation list" metric became "Wearable revocation list", which shows the published version and when it was published.
- Dashboard, org admin: the gateway list has a new "Revocation list" column, and the gateway page shows the same state with the warning when the gateway is behind. `revocation-list.ts` moved from `features/system` to `features/org`.
- Sample mode mirrors the API: registry answers drop the live fields, and org gateways carry `revocation`.

## Why
The system admin's job is to create organisations, register devices and grant them. Watching which devices and gateways are online, and whether a gateway enforces the latest list, belongs to the organisation that runs them. The API sent these fields to the system admin too, so hiding them in the dashboard alone was not enough.

## Evidence
- Backend, against a test database (podman): 227 integration tests passed in `test_revocation`, `test_access`, `test_gateways`, `test_registry` and `test_organisation`, including the new `test_tc_c11_the_system_admin_gets_no_live_status_of_devices` and the rewritten TC-C31 tests. 104 unit tests passed. The compose-stack tests (`test_ingestion`) were not run locally because the stack does not start under podman; they run in CI.
- Dashboard: typecheck and lint clean; 112 unit tests and 54 sample-data browser tests (desktop and phone) passed.
