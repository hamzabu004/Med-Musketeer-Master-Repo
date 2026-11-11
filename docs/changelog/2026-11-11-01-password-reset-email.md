# Password reset e-mail through Resend

- **Date:** 2026-11-11
- **Type:** code
- **Module:** M7 cloud
- **Commits:** 721469c (bootstrap, compose, tests, docs); this entry and the evidence in the next commit

## What changed
- **Bootstrap:** `app/zitadel_bootstrap.py` sets up ZITADEL's SMTP provider "MedMusketeer SMTP" from `SMTP_*` in `.env` on every `up`. It creates the provider once, then updates it, the password included so a rotated key takes effect, and makes it the active one. If `SMTP_HOST` is empty, ZITADEL's settings are left as they are. A host without a port, a missing sender or a bad `SMTP_TLS` value stops the job.
- **Compose:** the `zitadel-bootstrap` job receives `SMTP_*`. `mailpit` (`axllent/mailpit:v1.32.0`, `mail` profile, with a health check) catches ZITADEL's e-mail in development and in the stack tests and delivers none.
- **Production:** sends through Resend's SMTP (`smtp.resend.com:465`, user `resend`, the API key as the password) from `no-reply@medmusketeer.site`. The key is set by hand in the server's `cloud/.env` and is never committed.
- **Unchanged:** the API still sends no e-mail. Invite codes are shown once, as before.
- **Docs:** `cloud/README.md` ("E-mail (password reset)", the `mailpit` service), `.env.example`, `test_traceability.md` (TC-C43).

## Why
"Reset password" on ZITADEL's login page never sent its e-mail. The login accepted the request, but ZITADEL had no SMTP provider, so the notification failed and showed up only in ZITADEL's log. Until now no SMTP had been needed: the account flow returns invite codes and ZITADEL is asked not to send mail (`returnCode`). Password reset is the first flow that needs e-mail.

Resend was chosen for its free tier (3,000 e-mails a month, 100 a day, far more than the project sends) and for sending from the project's own domain, with DKIM and SPF.

## Evidence
`docs/testing/evidence/2026-11-11/password-reset-email/cloud/`, from `run_cloud_tests.sh` with `MM_COMPOSE="podman compose"`, run on `feat/mobile-relay` (92d85bc) with this change applied, before it moved to its own branch off `main` (CI runs the tests again there):
- `pytest.txt`: 433 passed, unit tests and the full compose-stack tests together.
- `stack/tc_c43_password_reset_mail.json`: the real ZITADEL v4.20.0 shows "MedMusketeer SMTP" as its active provider. The login's reset request e-mailed "Reset password" from the configured sender to the user, through Mailpit. The link goes to `/ui/v2/login/password/set` on the issuer's origin, and its code set a new password. The new password signs in and the old one is refused.
- TC-C01 now includes `mailpit`, which is healthy.

Not run: a real send through Resend. That needs the deployed server, the key in its `.env` and the verified domain. Check it after the deploy as in `cloud/README.md`, step 5.
