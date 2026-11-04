# The org admin gets a Gateways section, and gateway connectivity is logged (D17)

- **Date:** 2026-10-30
- **Type:** code, decision
- **Module:** M7 cloud, M8 dashboard
- **Commits:** pending

## What changed
- **Connectivity log** (migration 0005, `connectivity_events`): ingestion appends one row per change of state of a gateway's connection to the cloud, and of a wearable's presence through a gateway. A repeated state or an older report adds nothing, so the newest gateway row is when its current connection began (its uptime).
- **Alerts** record the gateway that attested them (`alerts.gateway_id`). Alerts stored before migration 0005 have none.
- **API** (`app/gateways.py`, org admin only): `GET /gateways`, `GET /gateways/{id}` (with the connected wearables), `GET /gateways/{id}/connectivity` and `GET /gateways/{id}/alerts`.
  - Alerts are given as time, wearable and patient only: an exception to D9 that leaves out the classification, confidence and ECG.
  - Other organisations' wearables on the gateway are counted, not named.
- **Dashboard:** a new "Gateways" section for the org admin.
  - The list shows each gateway's connection with uptime ("Up 3 h 20 min"), the wearables connected, alerts in the last 24 h, and when it was last heard from.
  - The gateway page shows the connected wearables with their patient and connected time, when alerts came through it, and the connectivity log with a filter.
  - Both pages re-read every 15 s.
  - The org dashboard counts gateways online, and the Devices page links to the gateway pages.
  - Sample data and `seed-dev` include a 20-minute outage and a wearable leaving for the mobile path.
- **Docs:** `cloud-backend.md` (D9 row and exception, endpoints, new D17), `iteration-6-dashboard.md` (org admin screens), `test_traceability.md` (TC-C33 to TC-C35, TC-D14).

## Why
The org admin could only see a gateway's "last heard from" on the Devices page. They could not see whether it was up or for how long, which wearables were on it, or when alerts came through it, and nothing kept a history of its connections. Showing alert times without their content was chosen (2026-10-30) so that D9 still keeps clinical data for doctors and patients.

## Evidence
`docs/testing/evidence/2026-10-30/gateway-view/`:
- `cloud/`: the full cloud suite (`run_cloud_tests.sh`), 416 passed, none skipped, including TC-C33 to TC-C35 and the TC-C09 matrix rows for `/gateways`.
- `dashboard/`: `vitest.txt` (TC-D14's unit tests), `playwright-mock.txt` (sample mode, desktop and phone), `lint.txt`, `typecheck.txt`.

Not run: the dashboard's API-mode browser tests (`scripts/api-e2e.sh`), which do not cover the gateway pages yet.
