# Code review findings — Slice 2 (database and registry)

- **Reviewed:** `main...feat/cloud-registry` (merged as 526710d), `/code-review` at medium effort, 2026-10-23
- **Status:** Open. Fixes deferred to the testing phase by the team; recorded here so they are not lost.
- **Verified so far:** finding 1 (FastAPI 0.161.1's `Depends` has `scope`; a `yield` dependency with the default scope runs its cleanup after the response is sent). The others are as reported, not yet re-checked.

| # | Severity | File | Finding | Failure scenario | Proposed fix |
|---|---|---|---|---|---|
| 1 | High | `cloud/backend/app/db.py` | The transaction commits only after the response has been sent (`Conn` is a default-scope `yield` dependency). | POST returns 201, then the commit fails: the client believes a record exists that was never stored; a quick follow-up request on another connection can see 404. | `Depends(connection, scope="function")`, and a test that a failed commit returns an error. |
| 2 | Medium | `cloud/backend/app/registry.py` (`grant_device`) | The device status check does not lock the device row, so it races with device revoke. | A revoked device ends up with an open grant. | `SELECT ... FOR SHARE` (or `FOR UPDATE`) on the device row. |
| 3 | Medium | `cloud/backend/app/registry.py` (`add_credential`) | Same race with device revoke. | A revoked device holds an active credential that later mTLS checks would accept. | Lock the device row before inserting. |
| 4 | Medium | `cloud/backend/app/registry.py` (`revoke_credential`) | Ignores the owning device and overwrites any status. | An active device is left with no valid credential; revoking an expired or already-revoked credential rewrites history and returns 200. | Only revoke `active` credentials (409 otherwise); decide whether revoking the last credential suspends the device. |
| 5 | Low | `cloud/backend/app/registry.py` (`close_grant`) | The UPDATE has no `revoked_at IS NULL`, and device revoke reads the grant without `FOR UPDATE`. | Two admins closing the same grant concurrently: the second overwrites who closed it and when. | Add `AND revoked_at IS NULL` and lock the grant row. |
| 6 | Low | `cloud/backend/app/db.py` | Only `IntegrityError` maps to an HTTP error. | A NUL byte in a name passes validation and returns 500 instead of 422. | Map `DataError` to 422 too. |
| 7 | Low | `cloud/backend/app/registry.py` (`list_credentials`, `list_grants`) | Return 200 `[]` for an unknown device. | A mistyped device id looks like "no credentials". | Return 404 for an unknown device; extend `test_unknown_records_return_404`. |
| 8 | Low | `cloud/backend/tests/integration/conftest.py` | The test database is assembled by hand (image tag + `docker cp`) instead of building `cloud/postgres/Dockerfile`. | The Dockerfile and the tests drift apart and tests pass against a different database. | Build and run `cloud/postgres/Dockerfile` in the fixture. |
| 9 | Low | `cloud/backend/tests/integration/conftest.py` | `engine_command` takes the first word of `MM_COMPOSE`. | `MM_COMPOSE=podman-compose` makes every database test error. | Add a separate `MM_ENGINE` setting (default `docker`). |
| 10 | Low | `cloud/compose.yaml` | `migrate` and `api` both build `./backend` with the same tag. | The backend image is built twice on every `up --build` (slow on the Pi). | Keep `build:` on one service; the other uses the image only. |

Lower priority, also reported: `revoke_grant` re-selects instead of using `RETURNING`; the status map duplicates `TRANSITIONS`; `migrations/env.py` has no offline (`--sql`) mode and no `dispose()` in a `finally`; `alembic_config` changes `os.environ` for the whole session; a naive `expires_at` is read in the database server's time zone.
