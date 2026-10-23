# Organisation-admin API, account creation in ZITADEL, and the access matrix (Iteration 3, Slice 3 part 2)

- **Date:** 2026-10-24
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/`

## What changed
- The `zitadel-bootstrap` job now also creates the API's own ZITADEL service account `mm-api` with the instance role `IAM_ORG_MANAGER`, and writes its token (valid for a year, replaced when missing or no longer working) to a new `mm-secrets` volume that only the job and the API mount. The API reloads it when ZITADEL refuses the old one (D12).
- `app/zitadel.py`: the API's ZITADEL client. Creating an organisation creates its ZITADEL organisation and grants it the MedMusketeer project with the roles `org_admin`, `doctor`, `patient`. Creating an account creates a human user in that organisation (e-mail as username), grants the role and returns an invite code; no password is set and no e-mail is sent. A failure in a later step deletes what was created.
- New endpoints (the full list is in D9 of `docs/decisions/cloud-backend.md`):
  - system admin: organisation admins (`POST /admin/organisations/{id}/admins`), the registry audit log, security events;
  - organisation admin: accounts (create, list, disable), patients, doctor assignment, wearable issue and return, disorders, patient export (without ECG for now), the organisation's audit log;
  - doctor and patient: alerts, alert acknowledgement (doctor), ECG segments with samples and classifications;
  - all organisation roles: own organisation; org admin and doctor: devices.
- Disabling a doctor ends their care assignments; disabling a patient returns their wearable and ends the monitoring session. The ZITADEL user is deactivated, and the API refuses the user's tokens at once.
- Migration 0002: `users.status` and the append-only `audit_log` table (D11); every registry and organisation action writes an entry in the same transaction.
- D9 got two rows (organisation admin accounts; patients list) and the rule that a patient outside the caller's reach answers 404, not 403.
- Query helpers moved from `app/registry.py` to `app/db.py`; `GET /me` also returns the patient id.
- `/code-review` reported 9 findings, recorded in `docs/testing/review-findings/2026-10-24-slice-3-org-admin.md`. Findings 1 to 3 were fixed before merging: issuing a wearable now locks the device grant, so it cannot race a grant revoke; issuing a wearable and assigning a doctor lock the user's row, so they cannot race a disable; and disabling an account that ZITADEL already shows as inactive now succeeds instead of failing on every retry. Findings 4 to 9 wait for the testing phase.

## Why
Slice 3 of `docs/iterations/iteration-3-cloud.md`: the organisation admin's part of the API, with accounts kept in step between ZITADEL and the database (D2), and the role × endpoint matrix tested in full.

## Evidence
243 tests pass (29 unit, the rest against a database container or the full stack). TC-C09: every endpoint × every role, plus a check that no endpoint is missing from the matrix. TC-C10 and TC-C11: data boundaries between doctors, patients, organisations and the system admin. TC-C13: against the real ZITADEL v4.20.0, an organisation, its admin, a doctor and a patient appear in the right ZITADEL organisation with the right role and in `users`, and disabling deactivates the ZITADEL user (`stack/tc_c13_accounts.json`). The review fixes have regression tests that fail without them. Evidence in `docs/testing/evidence/2026-10-24/cloud/`.
