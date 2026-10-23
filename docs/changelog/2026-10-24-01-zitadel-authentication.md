# ZITADEL authentication in the API (Iteration 3, Slice 3 part 1)

- **Date:** 2026-10-24
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/`

## What changed
- ZITADEL's first start now also creates an IAM_OWNER service account, `mm-bootstrap`. Its token is written only to the `zitadel-bootstrap` volume, which the API does not mount.
- A one-off `zitadel-bootstrap` job (`app/zitadel_bootstrap.py`) runs on every `up` and is idempotent. It creates the `MedMusketeer` project with role assertion and the roles `system_admin`, `org_admin`, `doctor`, `patient`. It grants `system_admin` to ZITADEL's first admin and writes the API's non-secret config (issuer, project id, default organisation id) to a new `mm-config` volume.
- The API validates ZITADEL JWT access tokens (`app/tokens.py`): RS256 only, a key from `/oauth/v2/keys` (refetched when an unknown key id appears, as ZITADEL rotates keys), the issuer, the project as audience, and `exp`/`nbf` with 30 s leeway.
- `app/auth.py` maps a token to a MedMusketeer user. The token must grant exactly one MedMusketeer role, granted by the user's own ZITADEL organisation. The user must be registered in `users` with the same role. An organisation user must belong to the organisation in the token and that organisation must be active. The system admin's token must come from the default organisation. Missing or invalid tokens get 401, valid tokens that do not match a user get 403, and a missing config gets 503.
- `GET /me` returns the caller's user id, role and organisation. `python -m app.manage register-user` registers a ZITADEL user, starting with the system admin.
- D2 corrected: the role claim is project-specific (`urn:zitadel:iam:org:project:{project_id}:roles`), verified against ZITADEL v4.20.0.
- Dependency added: PyJWT 2.15.1 (with `cryptography`), hash-locked.
- The dev stack was reset (`down --volumes`, only test data) so ZITADEL would create the service account; the first admin is registered as system admin.

## Why
Slice 3 of `docs/iterations/iteration-3-cloud.md`: every later endpoint depends on knowing who is calling.

## Evidence
57 tests pass: TC-C12 in unit form (local keys), against the database, and end to end with a real ZITADEL token (machine user, client-credentials grant), plus TC-C01 with both one-off jobs. Evidence in `docs/testing/evidence/2026-10-24/cloud/`.
