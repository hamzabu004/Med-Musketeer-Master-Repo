# Cloud database schema and system-admin registry (Iteration 3, Slice 2)

- **Date:** 2026-10-23
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/`

## What changed
- Alembic migration `0001` creates every table of the mid report's cloud schema, plus `organisations.zitadel_org_id` (D3). It is written as SQL. The database itself enforces: one open grant per device, one active wearable per patient and one patient per wearable, one active doctor per patient, one open monitoring session per device, a session's device/patient/organisation/path never change (trigger), a recording segment needs its command, and the system admin is the only user without an organisation.
- `ecg_chunks` and `security_events` are TimescaleDB hypertables on `ts`; raw `ecg_chunks` are dropped after a **90-day placeholder** retention period (still open); no foreign key points into `ecg_chunks`.
- Privileges: `mm_migrator` owns the schema; `mm_api` may only select, insert, update and delete rows.
- A one-off `migrate` service applies the migrations before the API starts.
- System-admin API under `/admin`: organisations (create, list, suspend), devices (register as pending, activate only with an active credential, suspend, revoke), credentials (add, list, revoke), device grants (grant to an active organisation, list, revoke). Revoking a device revokes its credentials and closes its grant; closing a grant ends the device's open assignment and monitoring session.
- `devices.is_testbed` has no default: it must be given when a device is registered, because attack tests are refused against production devices.
- Authentication is a placeholder that refuses every request until Slice 3, so `/admin` is unreachable in the running stack.
- The `postgres` and `proxy` images are now built with their configuration inside (`cloud/postgres/Dockerfile`, `cloud/traefik/Dockerfile`), and the stack has no bind mounts.

## Why
Slice 2 of `docs/iterations/iteration-3-cloud.md`. Docker Desktop's file sharing for the repository's drive returned "file exists" for paths it had mounted before (single files and directories alike), so the stack stopped depending on bind mounts; baked-in configuration also behaves the same on the Pi.

## Evidence
27 tests pass, 92% statement and branch coverage. Includes TC-C03 to TC-C08 against a real TimescaleDB container and TC-C01 against the full stack. Evidence in `docs/testing/evidence/2026-10-23/cloud/`.
