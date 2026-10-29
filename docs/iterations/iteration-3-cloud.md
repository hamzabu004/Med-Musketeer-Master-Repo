# Iteration 3 — Cloud backend

- **Owner:** Hamza Tariq (M7 cloud platform; M1 CA tool for the cloud certificate)
- **Status:** Slices 0 to 5 done (2026-10-29); Slice 6, the deployment to the cloud Pi, remains
- **Depends on:** `docs/decisions/stack.md`, `gaps.md`, the cloud schema in the mid report §5 "Data Design"
- **Followed by:** Iteration 4 (uplink bridge on the gateway → this backend)

## Goal

A cloud backend that a gateway could connect to: PostgreSQL + TimescaleDB with the device registry, organisations and device grants; ZITADEL with the four roles; the ingestion API; and EMQX with the gateway mTLS listener and a live credential check. A test script plays the gateway's part. It is developed with Docker Compose on the laptop and deployed to the second Raspberry Pi at the end.

## Scope

**In:**
- Compose stack: TimescaleDB, ZITADEL, EMQX, FastAPI backend (+ the MQTT ingestion adapter)
- Full schema as migrations (all tables of the report, so later iterations add code, not tables)
- Registry and organisation API for the system admin; account, device-issue and doctor-assignment API for the organisation admin
- ZITADEL: project, four roles, organisations, token validation and access rules in the API
- EMQX private-CA mTLS listener for gateways, live credential check, topic ACL
- Ingestion of gateway messages: alerts with their ECG segment, presence/status, IDS/IPS events
- A cloud server certificate profile in the CA tool (`cloud.medmusketeer.local`, serverAuth)
- Tests with TC-C IDs and stored evidence
- Deployment of the same stack to the cloud Pi, reachable over Tailscale

**Out (later iterations):**
- Uplink bridge on the gateway → Iteration 4
- Public-certificate listener for the phone relay, Let's Encrypt, public domain → Iteration 6
- Envelope verification, cloud classification, replay windows in use → Iteration 6
- Dashboard UI → Iteration 6 (this iteration only exposes the API it will use)
- Attack-test module → with IDS/IPS integration (Iteration 5)
- On-demand recordings (`telemetry`) ingestion → after the start/stop design is decided (gap)
- The registry link in the CA tool → may be pulled in at the end if time allows (`mmca revoke` was removed on 2026-10-29: revocation is done through the registry API)

## Exit criteria

1. `docker compose up` on the laptop and on the cloud Pi brings every service up healthy.
2. All migrations apply to an empty database; the schema matches the report's table list.
3. A test gateway with an active credential connects over mTLS; a revoked, unknown-CA, missing or wearable certificate is refused.
4. An alert published by the test gateway for an issued wearable lands in `monitoring_sessions`, `ecg_segments`, `ecg_chunks` and `alerts` with the right `patient_id`, `org_id` and `attested_by`; an alert for an unissued wearable is rejected and logged.
5. The role × endpoint matrix passes in full, including cross-organisation denial and "system admin sees no patient records".
6. Every TC-C test passes and its evidence is stored under `docs/testing/evidence/<date>/cloud/`.
7. `stack.md`, `gaps.md` and the change log are updated for every decision taken.

## Repository layout (proposed)

```
cloud/
├── compose.yaml            # timescaledb, zitadel, emqx, api, adapter
├── .env.example            # every variable, no secrets (.env is git-ignored)
├── backend/                # FastAPI app + adapter, one Python package
│   ├── pyproject.toml
│   ├── app/                # api/, auth/, registry/, ingest/, db/
│   ├── migrations/         # Alembic
│   └── tests/              # unit/ and integration/
├── emqx/                   # listener, authn/authz and rule config
├── zitadel/                # bootstrap script: project, roles, orgs, test users
└── run_cloud_tests.sh      # writes docs/testing/evidence/<date>/cloud/
shared/contracts/
├── ingest-v1.schema.json   # normalised message from adapters to the API
├── alert-payload-v1.schema.json  # fixed-path alert payload (shared with firmware)
├── status-v1.schema.json   # wearable and gateway presence (D15)
└── ids-event-v1.schema.json  # gateway IDS/IPS detections (D15)
```

## Slices

Each slice is one branch, merged after its tests pass and `/code-review` is clean, with a change-log entry. Sizes are relative: S (a day or two), M (several days), L (a week or more).

### Slice 0 — Decisions that block the code (S, no code)

**Done (2026-10-23).** All ten are Decided as proposed below, with D9 and D10 completed; the designs are in `docs/decisions/cloud-backend.md`, which is authoritative.

| # | Decision | Decided |
|---|---|---|
| D1 | How the ingestion side learns **which gateway published** a message (an MQTT subscriber cannot see the publisher) | An EMQX rule republishes every `mm/fixed/#` and `mm/gateway/#` message to an internal topic that carries the authenticated username (cert CN), e.g. `ingest/{username}/{original topic}`, readable only by the adapter. `attested_by` then comes from the broker, never from the payload. Alternative: EMQX HTTP action to the API. |
| D2 | Where the **role** lives (the report has `users.role`; Iteration 3 says "identity provider with the four roles") | Roles are ZITADEL project roles and arrive in the token; `users` keeps `zitadel_sub`, `role`, `org_id` as a mirror for joins, changed only through the API, which updates ZITADEL and the row together. |
| D3 | How **organisations** map to ZITADEL | One ZITADEL organisation per client organisation; the system admin sits in the instance's default organisation. `org_id` in the API comes from our `organisations` row linked to the ZITADEL org id. |
| D4 | **EMQX authentication** of gateways | mTLS with the private CA, cert CN as username, plus an HTTP authentication hook to an internal API endpoint that checks `devices.type = fixed_gateway`, `devices.status = active` and an active `x509_mtls` credential. HTTP authorisation hook for the ACL. Alternative: EMQX's PostgreSQL backends. |
| D5 | **Gateway ACL** on EMQX | Publish `mm/fixed/+/{alert,result,status,command_ack}` and `mm/gateway/{own id}/#`; subscribe `mm/fixed/+/command`. Observe-only for wearable↔gateway assignment in this iteration (the cloud records `current_gateway_id`, does not enforce). |
| D6 | **Alert payload v1** (shared with the firmware's Iteration 2 work) | The report's fields: `msg_id`, `seq`, `fs_hz`, `lead`, `n_samples`, `encoding` (little-endian int16, Base64), `samples`, `screening` (label, confidence, model version), `sent_at` (benchmark only). `msg_id` makes QoS 1 redelivery idempotent. |
| D7 | **Normalised ingestion message** (`ingest-v1`) | The adapter result from `stack.md` (`device_id`, `device_type`, `auth_method`, `attested_by`, `authenticated`, `auth_metadata`) + `msg_type`, `received_at`, hop timestamps, and the validated payload. |
| D8 | **Database access** | SQLAlchemy 2 (Core) + Alembic + psycopg 3; no ORM-heavy models. |
| D9 | **Role × endpoint matrix** | Table in `cloud-backend.md`, then one parametrised test. The organisation admin cannot read patient ECG data; a doctor sees the live status of their patients' devices and reads their disorders. |
| D10 | **EMQX version and licence** | `emqx/emqx:6.3.2` pinned (newest, 2026-10-16, amd64 + arm64). Business Source License 1.1: single-node production and academic use are allowed. |

### Slice 1 — Stack skeleton (S) — Done 2026-10-23

- `compose.yaml` with pinned image versions (all must have arm64 builds for the Pi): TimescaleDB 2.31.0 on PostgreSQL 18 (ZITADEL v4 supports 14–18), ZITADEL v4.20.0 (API and Login UI containers, behind Traefik v3.7.16 as in ZITADEL's reference compose, using the same Postgres instance with a separate database), `emqx/emqx:6.3.2`, `api` (Python 3.14.9). The `adapter` service is added in Slice 5.
- `.env.example`; health checks; `GET /healthz` on the API reporting database, ZITADEL and EMQX reachability.
- **Tests:** TC-C01 the stack comes up healthy from an empty volume; TC-C02 the API refuses to start without required settings.

### Slice 2 — Database and registry (M) — Done 2026-10-23

- Alembic migration with every table in the report; hypertables on `ecg_chunks.ts` and `security_events.ts`; the TimescaleDB retention policy on `ecg_chunks` (period as a setting).
- Constraints that enforce the rules: at most one open grant per device, one active wearable per patient, one active doctor per patient (partial unique indexes); sessions take `patient_id`/`org_id` from the active assignment and never change.
- System-admin API: organisations; devices (register pending → active, suspend, revoke); credentials; device grants and grant revocation.
- **Tests (real Postgres in a container):** TC-C03 migrations up and down on an empty DB; TC-C04 to TC-C06 each uniqueness rule rejects a second open row; TC-C07 revoking a grant ends the device's open assignment and session; TC-C08 registry endpoints round-trip.

### Slice 3 — IAM and access control (L) — Done 2026-10-24

**Part 1 (2026-10-24):** `zitadel-bootstrap` job (project, four roles, `system_admin` for ZITADEL's first admin, non-secret config written to the `mm-config` volume); token validation against ZITADEL's JWKS and mapping to `users` (`app.tokens`, `app.auth`); `GET /me`; `python -m app.manage register-user`; TC-C12 (unit, database and end-to-end with a real ZITADEL token).

**Part 2 (2026-10-24):** the API's ZITADEL service account `mm-api` (IAM_ORG_MANAGER, D12); organisations created in ZITADEL with the project granted; organisation-admin, doctor and patient accounts created in ZITADEL and `users` with an invite code, and disabled in both (`users.status`, migration 0002); patients, doctor assignment, wearable issue and return, disorders, exports; doctor and patient read endpoints for alerts and ECG segments, alert acknowledgement; `audit_log` for every registry and organisation action (D11); D9 matrix extended with two rows. TC-C09 to TC-C11, TC-C13. Not built: on-demand ECG requests (start/stop design open), test organisations and users in the bootstrap job (the tests create their own).

- ZITADEL bootstrap script: project, four roles, an API application, two test organisations, one test user per role per organisation, a machine user for the management API (key kept out of the repo).
- API: token validation against ZITADEL's JWKS; dependencies for role, organisation and doctor-assignment checks; patient and ECG queries filtered by `patient_id`/`org_id` from sessions and segments.
- Organisation-admin API: create doctor and patient accounts (through ZITADEL's management API), record disorders, issue a wearable to a patient, assign a doctor, export a patient. Every grant, issue, assignment and export is logged with the acting user.
- **Tests:** TC-C09 the role × endpoint matrix (every role × every endpoint, allowed or denied); TC-C10 a doctor cannot read a patient of another doctor or organisation; TC-C11 the system admin gets no patient or doctor data; TC-C12 expired, wrongly signed and wrong-audience tokens are refused; TC-C13 account creation shows up in ZITADEL and in `users`. Unit tests use locally signed tokens; integration tests use the ZITADEL container.

### Slice 4 — EMQX gateway listener (M) — Done 2026-10-24

**Done:** `mmca issue cloud`, and key identifiers on every certificate (found while testing: strict TLS clients refused mmca chains); an EMQX image with the configuration baked in and secrets rendered at start (D13); the gateway mTLS listener with the API's authentication hook matching the presented certificate to an active credential (D4, refined), the authorisation hook (D5) and the republish rule (D1), all verified on EMQX 6.3.2; an internal listener for the adapter; `scripts/install-emqx-certs.sh`; authentication decisions logged with their check time. TC-C14 to TC-C18. Not built: disconnecting a live gateway when its credential is revoked (`gaps.md`).


- CA tool: `mmca issue cloud` (server profile `cloud.medmusketeer.local`, serverAuth, EC P-256), with its own unit tests.
- EMQX: mTLS listener on 8883 with the private CA, cert CN as username, the authentication and authorisation hooks from D4/D5, the republish rule from D1. Connection events logged with timestamps (benchmark checkpoints later).
- **Tests (containers, same style as `test_broker_interop.py`):** TC-C14 an active gateway connects and publishes; TC-C15 a revoked credential is refused on the next connect; TC-C16 a foreign CA, no certificate, and a wearable certificate are refused; TC-C17 a publish or subscribe outside the ACL is denied (judged by the broker log or a monitor); TC-C18 the gateway verifies the cloud by CN/SAN pin.

### Slice 5 — Ingestion (M) — Done 2026-10-29

**Done:** the adapter (`app/adapter.py`, compose service `adapter`), the ingestion API (`POST /internal/ingest`, `app/ingest.py`) and the payload contracts in `shared/contracts/`, generated from `app/contracts.py` (D6, D7, D15). Also:
- migration 0003: `ingested_messages` for idempotency and hop times, `ecg_segments.lead`;
- the EMQX rule `mm_presence`, so gateway liveness comes from the broker's connect and disconnect events;
- `NOTIFY mm_alerts` on each new alert.

Tests TC-C20 to TC-C26, at the API against the database and end to end through EMQX. Test IDs moved up by one, because TC-C19 went to the dashboard sign-in (2026-10-25), and the gateway-down case got its own ID (TC-C26). Not built:
- the WebSocket alert push (the dashboard polls);
- ingestion of `telemetry`, `result`, `command_ack` and `backlog`;
- the mobile path (no adapter yet).

Alerts carry no severity: the wearable sends a label and a confidence, and neither the cloud nor the dashboard rates them (`alerts.severity` is nullable and unused).


- Adapter: subscribes to the internal topic from D1, validates against the contracts, builds `ingest-v1`, calls the ingestion API.
- Ingestion: alert → session (opened from the active assignment) + segment + chunks + alert row, idempotent on `msg_id`; status → `last_seen`, `current_gateway_id`, `current_mode`; gateway down → its wearables shown as unknown, not offline; `ids_event` → `security_events`; rejected messages logged with the reason.
- Alert push: `NOTIFY` on new alerts and a WebSocket endpoint that delivers them to the right doctor (stretch goal; the dashboard uses it in Iteration 6).
- **Tests:** TC-C20 an alert for an issued wearable lands in all four tables with `attested_by`; TC-C21 an alert for an unissued wearable is rejected and logged; TC-C22 a redelivered message is stored once; TC-C23 a malformed payload is rejected; TC-C24 an IDS event is stored; TC-C25 reassigning a wearable ends the session, so later data goes to the new patient; TC-C26 a gateway going offline shows its wearables as unknown, not offline.

### Slice 6 — Deploy to the cloud Pi (S)

- Same compose stack on the second Pi (arm64), reachable over Tailscale; volumes and a database backup script; secrets in the Pi's `.env` only.
- Decide disk encryption on the Pi (the report plans encryption at rest with the cloud platform) or record it as an accepted shortcut.
- **Tests:** TC-C27 the smoke suite (C01, C14, C20) passes against the Pi from the laptop; memory and CPU use recorded at idle.

## Testing approach

- `pytest` with markers: `unit` (no containers), `integration` (Postgres, ZITADEL, EMQX containers). The CA-tool suite keeps running unchanged.
- TC-C IDs are added to `docs/testing/test_traceability.md` as each test lands.
- `cloud/run_cloud_tests.sh` stores the environment, `pytest.txt`, `junit.xml`, `coverage.xml` and broker logs under `docs/testing/evidence/<date>/cloud/`, like `run_report_tests.sh`.
- No mocks for the database or the broker in integration tests; mocks only where a real service cannot run (e.g. ZITADEL failure modes).

## Risks

| Risk | Mitigation |
|---|---|
| ZITADEL setup is the largest unknown (bootstrap, token claims, management API) | Start Slice 3's bootstrap early, in parallel with Slice 2; keep the API's auth behind one module so unit tests do not need ZITADEL |
| The Pi's memory may not hold Postgres + ZITADEL + EMQX + the API | Record its model and RAM before Slice 6; measure idle use on the laptop first; fall back to a VM if needed |
| The alert payload (D6) must match what the firmware sends | Keep the schema in `shared/contracts/` and share it with the Iteration 2 firmware work before Slice 5 |
| EMQX licence terms change in a later version | D10: 6.3.2 is pinned and its BSL 1.1 terms checked; any upgrade re-checks the licence and gets a change-log entry |
| Open gaps (on-demand start/stop, `status` semantics) | Out of scope here; ingestion rejects unknown message types with a logged reason |

## Order

Slice 0 → Slice 1 → Slices 2 and 3 (the ZITADEL bootstrap can start alongside Slice 2) → Slice 4 → Slice 5 → Slice 6.
