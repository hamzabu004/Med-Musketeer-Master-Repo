# A push to main deploys to the server; the system admin's security sections are hidden

- **Date:** 2026-11-04
- **Type:** ops
- **Module:** M7 cloud | M8 dashboard
- **Commits:** pending

## What changed
- A new workflow, `.github/workflows/deploy.yml`, deploys `main` to the Oracle VM at `medmusketeer.site`. It waits until every test workflow the commit started (`Dashboard`, `Cloud backend`) has passed. It then calls `cloud/scripts/deploy.sh` over SSH with a key restricted to that script, and the script checks out the commit and rebuilds the stack. `cloud/README.md` ("Continuous deployment") describes the trigger, the secrets, the manual redeploy and the rollback.
- `~/medmusketeer` on the VM is now a sparse git clone (`cloud`, `shared`, `web/dashboard`) instead of a copied tree. `cloud/.env` and the data volumes were kept.
- The dashboard's screen text no longer names ZITADEL.
- The system admin's menu no longer has Security Events or Attack Tests, and their Dashboard no longer shows the latest security events. The pages, their code and the API are unchanged and can still be opened by address.

## Why
Before this, the site changed only when someone copied the files to the VM and rebuilt by hand. Security events and attack tests wait on the IDS/IPS integration (Iteration 5), so the system admin does not need them yet. ZITADEL is a product name that the dashboard's users do not need to know.

## Evidence
pending: the first automatic deploy's workflow run.
