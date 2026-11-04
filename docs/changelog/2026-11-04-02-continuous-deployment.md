# A push to main deploys to the server; the system admin's security sections are hidden

- **Date:** 2026-11-04
- **Type:** ops
- **Module:** M7 cloud | M8 dashboard
- **Commits:** 9ac0616 (ZITADEL text), 9f8db71 (security sections hidden), c33d650 and e3bef9d (deployment); merged to main as 5370be0 (PR #11)

## What changed
- A new workflow, `.github/workflows/deploy.yml`, deploys `main` to the Oracle VM at `medmusketeer.site`. It waits until every test workflow the commit started (`Dashboard`, `Cloud backend`) has passed. It then calls `cloud/scripts/deploy.sh` over SSH with a key restricted to that script, and the script checks out the commit and rebuilds the stack. `cloud/README.md` ("Continuous deployment") describes the trigger, the secrets, the manual redeploy and the rollback.
- `~/medmusketeer` on the VM is now a sparse git clone (`cloud`, `shared`, `web/dashboard`) instead of a copied tree. `cloud/.env` and the data volumes were kept.
- The dashboard's screen text no longer names ZITADEL.
- The system admin's menu no longer has Security Events or Attack Tests, and their Dashboard no longer shows the latest security events. The pages, their code and the API are unchanged and can still be opened by address.

## Why
Before this, the site changed only when someone copied the files to the VM and rebuilt by hand. Security events and attack tests wait on the IDS/IPS integration (Iteration 5), so the system admin does not need them yet. ZITADEL is a product name that the dashboard's users do not need to know.

## Evidence
- Dashboard (before merging): typecheck and lint clean, 111 unit tests and 32 sample-data browser tests (sign-in, system admin) passed.
- `deploy.sh`, tested in a clone of the repository: it refuses anything other than a full commit SHA, refuses a commit not on `main`, and does nothing when a newer commit is already deployed. The deploy key's forced command allows no shell.
- First automatic deploy, 2026-11-04, of 5370be0: [Dashboard](https://github.com/hamzabu004/Med-Musketeer-Master-Repo/actions/runs/41785768146) and [Cloud backend](https://github.com/hamzabu004/Med-Musketeer-Master-Repo/actions/runs/41785768117) passed. The first [Deploy run](https://github.com/hamzabu004/Med-Musketeer-Master-Repo/actions/runs/41786042308) waited because Cloud backend was still running. The [second](https://github.com/hamzabu004/Med-Musketeer-Master-Repo/actions/runs/41786278046) deployed it, and all eight services reported healthy.
- After the deploy: `app` answered 200, the API's `/auth/config` and ZITADEL's discovery document answered 200, and port 8883 accepted connections. The served dashboard's system admin menu has Dashboard, Organisations, Devices, Audit Log and Account only.
