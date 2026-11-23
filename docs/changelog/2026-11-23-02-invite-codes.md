# Invite codes: clearer login texts and a new code for a lost one

- **Date:** 2026-11-23
- **Type:** code
- **Module:** M7 cloud, M8 dashboard
- **Commits:** 2f95c53 (API, bootstrap, dashboard, tests, docs); this entry and the evidence in the next commit

## What changed
- **Login texts:** `app/login_texts.py` overrides the English texts of ZITADEL's login where the defaults misled:
  - The invite code page now says "Enter the invite code your administrator gave you." It used to say "Enter the Code provided in the verification email."
  - Its resend link now reads "E-mail me a new code (the old one stops working)", under "Lost the code? Ask your administrator for a new one."
  - A refused code says that a code stops working once a new one is sent.
  - The label "Loginname" becomes "Login Name".
  - A wrong password gets a plain message instead of "Could not create session for user".
- **How the texts are applied:** the `zitadel-bootstrap` job sets the texts on the instance and on every organisation, and leaves them alone when they are already in place. ZITADEL v4.20 does not pass the instance's texts on to an organisation, and only an instance owner may set an organisation's. So an organisation created since the last deploy shows ZITADEL's defaults until the next deploy. That is the user's choice over a long-running sync service holding the owner token.
- **New invite code (API):** `POST /accounts/{id}/invite_code` lets the org admin get a new code for a doctor or patient. `POST /admin/organisations/{org}/admins/{id}/invite_code` lets the system admin get one for an organisation admin. Each returns a new code once, and the old code stops working. The API answers 409 for a disabled account, and for an account that already has a password or passkey (ZITADEL's "User is already initialized"). Each new code is audited as `account.invite_code`.
- **Dashboard:**
  - "New invite code" button, with a confirmation, on the org admin's Accounts table and on the system admin's "Administrators created" table. The code is shown once, like a new account's.
  - The code box now warns that a code e-mailed by the sign-in page replaces it.
  - The "Using your invite code" page warns against "E-mail me a new code" and replaces the confusing step "You return here signed in, to the pages your role allows".
- **Deploy:** `scripts/deploy.sh` re-creates `zitadel-login` after `up`. The login keeps the settings and texts it read for up to an hour, so without this a change made by the bootstrap would show only later.
- **Docs:** `cloud/README.md` ("ZITADEL set-up", routes, "Continuous deployment"), D12 in `docs/decisions/cloud-backend.md`, `test_traceability.md` (TC-C45, TC-C46, TC-D05).

## Why
In the FYP website review, a new organisation admin could not sign in with their invite code. The report said "session expired". The live server's log from 2026-11-20 shows what happened:
1. At 06:02:26 UTC the login sent the user a new invite e-mail (`"context":"verify","isInvite":true`). That is the "Resend code" link on the code page.
2. The new code replaced the administrator's code, and it went to the made-up e-mail address the account was created with.
3. The reviewer then entered the administrator's code three times, and each attempt failed with "Code is invalid (COMMAND-Wgn4q)".

The page invited this mistake: it asked for a code "provided in the verification email" when the code had come from the administrator. On a local copy of the stack, no other route reproduced the failure: Back, reload, a wrong code first, the account chooser, and the passkey path all worked. Once a code was lost or replaced, the only way out was to delete the account and create it again.

## Evidence
`docs/testing/evidence/2026-11-23/invite-codes/cloud/`, from `run_cloud_tests.sh` with `MM_COMPOSE="podman compose"`:
- `pytest.txt`: 449 passed, unit tests and the full compose-stack tests together. The first run failed once in TC-C29 with the known `SSLEOFError` after EMQX is recreated, which is unrelated; the run here is the full rerun.
- `stack/tc_c45_login_texts.json`: on the real ZITADEL v4.20.0:
  - An organisation the API creates has no texts of its own until the bootstrap runs again, and has them afterwards.
  - The sign-in page shows "Login Name".
  - That organisation's new admin's invite code page shows the three new texts and no "verification email".
- `stack/tc_c46_new_invite_code.json`: the system admin's new code makes the first one fail with "Code is invalid (COMMAND-Wgn4q)", the same error as in the review, and the new one verifies. After a password is set, a further code is refused with 409. The audit log holds `account.invite_code`.

Dashboard, run locally and not stored:
- `vitest`: 115 passed.
- Sample-mode Playwright: 56 passed, desktop and phone.
- API-mode Playwright through `scripts/api-e2e.sh`: 9 passed. In it, the new org admin's first code is replaced and the admin signs up with the new one.
