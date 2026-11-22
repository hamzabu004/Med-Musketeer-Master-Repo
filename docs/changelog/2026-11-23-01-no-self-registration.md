# Self-registration turned off in ZITADEL's login

- **Date:** 2026-11-23
- **Type:** code
- **Module:** M7 cloud
- **Commits:** f8a4fb4 (bootstrap, tests, docs); this entry and the evidence in the next commit

## What changed
- **Bootstrap:** `app/zitadel_bootstrap.py` turns off self-registration (`allowRegister`) in ZITADEL's default login policy on every `up`. The policy's other settings (password and passkey sign-in, password reset, check lifetimes) are sent back as they were read. A policy that already has registration off is left alone, and a refused update stops the job. The organisations the API creates have no login policy of their own, so they all use this one.
- **Login page:** "Register new user" is gone from the sign-in page. Opening `/ui/v2/login/register` directly shows ZITADEL's "Registration disabled. Please contact your administrator." With registration on, the login also sent an unknown login name to the register page, filled in as the e-mail. That no longer happens.
- **Delay on a running server:** ZITADEL's login keeps the login settings in memory for 15 minutes, so after the deploy the button can stay for up to that long. `docker compose restart zitadel-login` removes it at once (`cloud/README.md`).
- **Unchanged:** accounts are still created by an administrator, and the person redeems the invite code in ZITADEL's login to set a password or passkey (D12).
- **Docs:** `cloud/README.md` ("ZITADEL set-up"), D12 in `docs/decisions/cloud-backend.md`, `test_traceability.md` (TC-C44).

## Why
In the FYP website review, most of the problems on the login pages came from "Register new user". A self-registered user had no role and no organisation, so they always ended up on the dashboard's "No access" page. Along the way the reviewer hit several confusing details of ZITADEL's register page: the login name copied into the e-mail field, numbers allowed in names, "Could not create user" for an existing user, passkey registration failing, and no e-mail on registering. In this system only an administrator creates accounts, so the register page had no use. Turning it off removes the whole group of problems.

## Evidence
`docs/testing/evidence/2026-11-23/no-self-registration/cloud/`, from `run_cloud_tests.sh` with `MM_COMPOSE="podman compose"`, run on this branch with f8a4fb4's changes:
- `pytest.txt`: 434 passed, unit tests and the full compose-stack tests together.
- `stack/tc_c44_no_self_registration.json`: on the real ZITADEL v4.20.0, the default login policy has `allowRegister: false` with password sign-in, passkeys and password reset unchanged. A new organisation inherits it (`RESOURCE_OWNER_TYPE_INSTANCE`). The login's sign-in form draws no register button (`data-testid="register-button"`, which ZITADEL's login draws only when the settings allow registration), and its register page shows "Registration disabled".

Not tested live: the button coming back with registration on. The login's 15-minute settings cache means a policy changed during the test does not reach the page, so the test relies on the login's source (v4.20.0) for that side.
