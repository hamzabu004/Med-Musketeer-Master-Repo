# Iteration 6 — Dashboard

- **Owner:** Hamza Tariq (M8 dashboard)
- **Status:**
  - The screens for all four roles are built and tested in both data modes (2026-10-26, branch `feat/dashboard`).
  - Deployment on the cloud Pi is not set up yet.
  - Live alert push and on-demand recording wait for cloud work (below).
- **Depends on:** the cloud API of Iteration 3 (D9 access matrix and D14 sign-in in `docs/decisions/cloud-backend.md`), `stack.md` (liveness, the latency methodology), `scope.md` (roles)
- **Code:** `web/dashboard/` (`README.md` there has run and test commands)
- **Replaces:** the POC-Lite proof of concept. That was built before the system existed, on mock data with heart rate, editable monitoring stations and three roles.

## Goal

A web dashboard on the cloud API for the four roles of `scope.md`. Each role sees what D9 allows and nothing more, so the API enforces access and the dashboard only arranges it.

## Data modes

| Mode | Data | Sign-in | Use |
|---|---|---|---|
| `api` (default) | The cloud API at `NEXT_PUBLIC_API_URL` | ZITADEL, authorization code + PKCE; settings from `GET /auth/config` | Real deployments, the API-mode browser tests |
| `mock` | Sample data in the browser, kept in `sessionStorage` | Pick a sample account | A demonstration without the cloud, the sample-mode browser tests |

- The sample data has the same people, devices and synthetic ECG as `seed-dev`, plus a second organisation.
- It applies the API's D9 rules (403 for a role, 404 out of reach) and its state rules (409/422), so a screen behaves the same in both modes.
- The modes are never mixed. A feature the cloud does not serve yet is marked unavailable in API mode (`src/config/capabilities.ts`), never filled with sample data.
- Sample mode shows "Sample data" in the header.

## Screens

Every list loads with a skeleton, says when it is empty, and shows an error with Retry. Every change reports its outcome. Each page fits a phone screen, and tables scroll inside their own box.

### All roles
- **Sign-in:**
  - ZITADEL's login (password or passkey);
  - an account ZITADEL accepts but the API refuses gets a "no access" page, which names a suspended organisation;
  - the invite-code page explains how to redeem a code at first sign-in.
- **Account:** name (from `/directory`), role, organisation, sign-out (which also ends the ZITADEL session), and where to change the password.
- **Area guard:** each role has its own area (`/system`, `/org`, `/doctor`, `/patient`). A visitor outside their area goes to their own dashboard, and a signed-out visitor goes to sign-in.

### System administrator (sees no patient data)

| Screen | Content and actions | Endpoints |
|---|---|---|
| Dashboard | Organisation and device counts by status; latest security events and registry changes | `/admin/organisations`, `/admin/devices`, `/admin/security-events`, `/admin/audit` |
| Organisations | List; create (public/private) | `GET/POST /admin/organisations` |
| Organisation | Suspend or reactivate, saying that every member is refused while suspended; create an organisation admin with the invite code shown once; administrators created; devices granted | `PATCH /admin/organisations/{id}`, `POST /admin/organisations/{id}/admins` |
| Devices | List with filters; register by certificate UUID, type and testbed flag | `GET/POST /admin/devices` |
| Device | Facts and liveness; activate (needs an active credential), suspend, revoke with its cascade spelled out; add a credential by SHA-256 fingerprint, revoke it; grant to an organisation, end the grant, grant history | `/admin/devices/{id}/…` |
| Security events | Filter by mode, class and outcome; detail panel | `GET /admin/security-events` |
| Attack tests | Start and stop against testbed devices only; results compare each window with the IDS events (detected after N s, missed, not covered) | Not served yet (Iteration 5); sample mode only |
| Audit log | Registry changes, filtered by kind | `GET /admin/audit` |

### Organisation administrator (sees no ECG, classifications or alerts)

| Screen | Content and actions | Endpoints |
|---|---|---|
| Dashboard | Organisation; doctors, patients, wearables issued and free, gateways; patients without a doctor or wearable; latest changes | `/organisation`, `/accounts`, `/patients`, `/devices`, `/audit` |
| Accounts | List with names and e-mail, filtered by role and status; create a doctor or patient (a patient needs a pseudonym), with the invite code shown once; disable a doctor or patient, with the consequences for their patients or wearable spelled out | `GET/POST /accounts`, `POST /accounts/{id}/disable`, `/directory` |
| Patients | Search; filter by no doctor, no wearable, or disabled account | `/patients`, `/directory` |
| Patient | Assign or change the doctor; issue a free active wearable, return it; record disorders; export for a named destination (summary, record, JSON download); history from the audit log | `PUT /patients/{id}/doctor`, `POST/DELETE /patients/{id}/wearable`, `GET/POST /patients/{id}/disorders`, `POST /patients/{id}/exports` |
| Devices | Devices granted to the organisation, read-only: status, path, gateway, last heard from, patient | `GET /devices` |
| Audit log | The organisation's changes, with people by name and patients by pseudonym | `GET /audit` |

### Doctor (own current patients only)

| Screen | Content and actions | Endpoints |
|---|---|---|
| Dashboard | Unacknowledged alerts with acknowledge; patients; wearables heard from in the last 15 minutes | `/alerts?unacknowledged=true`, `/patients`, `/devices` |
| Alerts | Unacknowledged or all; acknowledge; new alerts since the page opened | `GET /alerts`, `POST /alerts/{id}/acknowledge` |
| Alert | Classification, confidence, where it was classified (gateway on the fixed path, cloud on the mobile path); its ECG segment and every classification; acknowledge | `GET /alerts`, `GET /segments/{id}` |
| Patients | Pseudonym, name, unacknowledged count, wearable path and last contact | `/patients`, `/devices`, `/alerts` |
| Patient | Wearable status; known disorders; alerts; ECG segments; on-demand recording | `/patients/{id}/alerts`, `/patients/{id}/segments`, `/patients/{id}/disorders` |
| ECG segment | The strip and the classifications | `GET /segments/{id}` |

### Patient (themselves only)

| Screen | Content | Endpoints |
|---|---|---|
| Dashboard | Organisation, their doctor's name, latest alerts, the "research prototype, not a medical device, not medical advice" notice | `/organisation`, `/directory`, `/alerts` |
| Alerts | Their alerts, read-only, with who acknowledged each; each opens its ECG | `GET /alerts` |
| ECG recordings | Their segments and the viewer | `/patients/{id}/segments`, `/segments/{id}` |

## Display rules

- **ECG strip:**
  - samples decoded from int16le-base64 chunks, stitched by `seq`, at the segment's `fs_hz`;
  - drawn at 25 mm/s and 10 mm/mV on 1 mm / 5 mm squares, keeping paper proportions, with a readout of time and voltage;
  - the gain is assumed to be 200 counts/mV (MIT-BIH), and the strip says so.
- **Liveness:**
  - the dashboard shows registry status, the path last used and when the cloud last heard from a device;
  - it never says offline: a quiet wearable may have changed path, or its gateway may be unreachable (`stack.md`, liveness);
  - how the two paths reconcile is open.
- **Names:**
  - from `/directory` (ZITADEL);
  - if ZITADEL is unreachable, pages still work with ids and say so;
  - patients appear by pseudonym, with the name only where the role may see it.
- **Errors:** a 404 reads "Not found, or not available to you", because D9 does not tell the two apart. Constraint conflicts (409) get plain messages.
- **Invite codes:** shown once and kept on screen until the admin confirms they passed it on, even if the page fails to reload; "Copied" only when copying worked.
- **Alert refresh:**
  - alert screens poll every 15 s while visible (only the alerts, not the lists behind them);
  - counts from lists the API caps at 1000 read "1000+".
- **Latency checkpoint:**
  - `performance.mark("mm:dashboard-render", { detail: { alert_id, created_at, backlog } })` the first time each alert is drawn;
  - `backlog` marks alerts older than the page, so analysis can leave them out;
  - a latency run uses an unfiltered alert list.
  - It is for measurement only.
- **Tokens:**
  - kept in `sessionStorage` only;
  - renewed with the refresh token, one renewal at a time;
  - a session that can no longer be renewed signs out.

## Waiting for the cloud

| Feature | Dashboard now | Needs |
|---|---|---|
| Live alert push | Polls every 15 s | Slice 5 ingestion with `NOTIFY` and a WebSocket |
| On-demand recording | Unavailable in API mode. Sample mode follows a provisional contract shaped on `commands` (sent, acked, expired) and the `recording` segment | The start/stop design (`gaps.md`), then an endpoint |
| Attack tests | Unavailable in API mode; sample mode only | Iteration 5 endpoints |
| A single alert | Searched for among the newest 1000 unacknowledged and newest 1000 alerts | `GET /alerts/{alert_id}` |
| Organisation admins, for the system admin | Read from `account.created` audit rows (newest 1000) | An endpoint listing an organisation's admins |
| Devices granted to an organisation, for the system admin | One grants request per device | Grants filtered by organisation |
| One patient, for the org admin | Organisation-wide lists, and the patient's history from the newest 1000 audit rows | `GET /patients/{id}` and an audit filter by target |
| Long histories | Audit, security events and alerts read the newest 1000 | Paging |

**Severity (2026-10-29):** alerts carry no severity (`cloud-backend.md` D15), so the dashboard shows none: no column, filter, detail row or high-severity count.

## Deployment

- The dashboard is served from the **cloud Pi**, next to the cloud stack. It is not hosted on Vercel.
- This is not set up yet. It belongs with the cloud's deployment to the Pi (Iteration 3, Slice 6) and its public domain with a Let's Encrypt certificate (`stack.md`, "Certificate scope").
- What the deployment has to provide:
  - a build in API mode with `NEXT_PUBLIC_API_URL` set to the cloud's public address;
  - `next start`, or a container, behind the stack's reverse proxy;
  - the dashboard's https origin in `DASHBOARD_ORIGINS`, so that the ZITADEL app's redirect URIs and the API's CORS match it (all-https origins turn ZITADEL's dev mode off).
- **Open:** D14 chose CORS over a same-origin proxy because the dashboard was to be hosted on Vercel. Served by the same proxy as the API, it could share the API's origin, and CORS would not be needed. Decide when the Pi deployment is built.

## Tests

The cases are TC-D01 to TC-D12 in `docs/testing/test_traceability.md`.
- **Unit tests (Vitest):** run with `npm test` in `web/dashboard/`.
- **Sample-mode browser tests (Playwright):** desktop and phone; run with `npm run test:e2e`.
- **API-mode browser tests:** `scripts/api-e2e.sh`. It brings up the cloud stack under its own compose project, seeds it with `seed-dev`, signs in through ZITADEL's real login, and removes the stack afterwards.
- **Evidence:** `docs/testing/evidence/2026-10-26/dashboard-phase-{4,5,6}/` (Phase 3's is in `dashboard/`).
