# MedMusketeer — Cloud Backend Design (Iteration 3)

Companion to `stack.md`. Records decisions D1 to D10 from Slice 0 of `docs/iterations/iteration-3-cloud.md`, D11 and D12 taken while building Slice 3, D13 from Slice 4, D14 for the dashboard and D15 from Slice 5. Status markers follow `stack.md`. All are **Decided** (D1 to D10 on 2026-10-23, D11 to D13 on 2026-10-24, D14 on 2026-10-25, D15 on 2026-10-29). D1, D4 and D5 are **Implemented** and container-tested (Slice 4, TC-C14 to TC-C18); D6, D7 and D15 likewise (Slice 5, TC-C20 to TC-C26). Details marked "verify in Slice N" are to be confirmed against the pinned versions while building.

Last updated: 2026-10-29

## Overview

```
 test gateway (gateway cert from mmca)
        │  MQTT over mTLS, port 8883
        ▼
┌────────────────────── EMQX 6.3.2 ─────────────────┐
│ 1. TLS: chain must lead to the private CA         │
│ 2. username = cert CN (the gateway's device_id)   │
│ 3. authn hook ─────► API /internal/emqx/authn ─┐  │
│ 4. authz hook ─────► API /internal/emqx/authz ─┤  │
│ 5. rule: mm/fixed/#, mm/gateway/#              │  │
│      └► republish to ingest/{username}/{topic} │  │
└──────────────────────┬─────────────────────────┼──┘
                       │ only the adapter may    │
                       │ subscribe to ingest/#   │
                       ▼                         ▼
                 MQTT adapter ──ingest-v1──► FastAPI ───► PostgreSQL + TimescaleDB
                                               ▲   │            │ NOTIFY on new alert
 test client / later dashboard ── OIDC token ──┘   │            ▼
        ▲                                          │      WebSocket alert push
        └─── login ─── ZITADEL ◄── management API ─┘
```

## D1 — The broker, not the payload, says which gateway published (Decided)

An MQTT subscriber sees the topic and payload but not the publisher, so `attested_by` taken from the payload could be forged by another gateway.

```
gateway (CN = gw-7f3a…)                 EMQX                          adapter
   │ PUBLISH mm/fixed/{wearable}/alert   │                               │
   │────────────────────────────────────►│ authz: allowed for this CN?   │
   │                                     │ rule fires, republishes:      │
   │                                     │ ingest/gw-7f3a…/mm/fixed/{wearable}/alert
   │                                     │──────────────────────────────►│
   │                                     │       attested_by = gw-7f3a…  │
```

- An EMQX rule selects `username`, `topic`, `payload` (and timestamps) from `mm/fixed/#` and `mm/gateway/#` and republishes to `ingest/${username}/${topic}`.
- Only the adapter's account may subscribe to `ingest/#`; no device may publish to it.
- The adapter takes `attested_by` from the `ingest/{username}/…` prefix.
- Rejected alternative: an EMQX HTTP action per message to the API (one HTTP call per message; the adapter would stop being an MQTT subscriber like the other adapters).
- Verified in Slice 4 (2026-10-24, EMQX 6.3.2): rule `mm_ingest` selects `id, username, clientid, topic, qos, payload, publish_received_at` from both topic filters and republishes to `ingest/${username}/${topic}` with the same QoS. The republished payload is that selection as JSON: the original payload as a string, `username` (the gateway's CN) and `publish_received_at` (broker receive time, ms since the epoch, the `broker_at` hop of D7).
- The adapter logs in on a separate internal listener (D13) and may only subscribe to `ingest/#`; gateways may not read or write `ingest/` (TC-C17).

## D2 + D3 — Roles in ZITADEL, one ZITADEL organisation per client organisation (Decided)

```
ZITADEL instance
├── Default org ─────────── system admin user(s)
├── Org "Hospital A"  ◄─┐
│     ├── org admin      │  project "MedMusketeer" is granted to each org
│     ├── doctors        │  project roles: system_admin, org_admin, doctor, patient
│     └── patients       │
└── Org "Clinic B"    ◄─┘

Token claims the API reads:
  sub                                          → users.zitadel_sub
  urn:zitadel:iam:org:project:{project_id}:roles → role → {granting org id: domain}
  urn:zitadel:iam:user:resourceowner:id        → ZITADEL org id → organisations.org_id
```

```
Postgres (mirror)
organisations: org_id, name, kind, status, zitadel_org_id   ← column added to the report's schema
users:         user_id, zitadel_sub, role, org_id, status   ← mirror for joins; changed only by the API
```

- ZITADEL is the source of truth for the role. The API authorises from the token's role and takes `org_id` from `organisations`.
- The API is the only path that changes a role: it updates ZITADEL and the `users` row in one operation.
- `users.status` (`active`/`disabled`, migration 0002, 2026-10-24): disabling an account deactivates the ZITADEL user and sets the row to `disabled`; the API refuses a disabled user's tokens at once, without waiting for them to expire.
- Creating an organisation creates its ZITADEL organisation and grants it the project with the roles `org_admin`, `doctor`, `patient` (verified against v4.20.0 on 2026-10-24); `organisations.zitadel_org_id` links the two.
- Verified in Slice 3 (2026-10-24) against ZITADEL v4.20.0: the role claim is project-specific, `urn:zitadel:iam:org:project:{project_id}:roles`, and maps each role to the organisation that granted it; the API also requires that this is the user's own organisation (`resourceowner:id`). `aud` is the project id, tokens are RS256-signed with keys from `/oauth/v2/keys`, and machine users must use `ACCESS_TOKEN_TYPE_JWT` (the API validates JWTs only). A project grant per client organisation plus a user grant gives a client-organisation user their role.

## D4 — Gateway authentication: mTLS + HTTP hook (Decided)

```
gateway ── TLS handshake ──► EMQX
           chain → private CA?          no → refused
           client cert present?         no → refused
           username := cert CN          (mqtt.peer_cert_as_username = "cn")
EMQX ── POST /internal/emqx/authn {username, clientid} ──► API
API checks:
  devices.device_id = CN
  devices.type      = fixed_gateway     (a wearable cert is refused here)
  devices.status    = active
  device_credentials: active x509_mtls row, not expired
→ {"result": "allow" | "deny"}   (check time logged; a benchmark checkpoint later)
```

- Listener: `verify = verify_peer`, `fail_if_no_peer_cert = true`, `cacertfile` = the MedMusketeer CA.
- **Refined in Slice 4 (2026-10-24): the presented certificate itself must be the credential.** EMQX passes the client certificate (`${cert_pem}`) to the hook; the API requires its SHA-256 fingerprint to be an active, unexpired `x509_mtls` credential of that device, so revoking one certificate refuses it at once even if the gateway has another. For `x509_mtls`, `device_credentials.credential_ref` is therefore the certificate's SHA-256 fingerprint as `mmca issue` prints it (64 hex digits; the registry API checks the format and normalises it). The hook also checks that the certificate CN equals the username and that the request came from the gateway listener.
- EMQX calls the hooks with a shared secret (`Authorization: Bearer`, `EMQX_HOOK_SECRET`); without it, or on any API error, EMQX treats the hook as "ignore" and the client is refused (verified: with the API unreachable, connections are refused). Each decision is logged by the API with its reason and check time in ms.
- A revoked credential is refused at the next connect. The revoke endpoint may also disconnect the client through EMQX's API.
- The API must answer with HTTP 200/204; a 4xx/5xx is ignored by EMQX and the chain continues, so the chain must end in deny.
- Rejected alternative: EMQX's built-in PostgreSQL backends (logic split between EMQX config SQL and the API).

## D5 — Gateway ACL, observe-only assignment (Decided)

| Direction | Topic | Note |
|---|---|---|
| Publish | `mm/fixed/+/alert` | Forwarded wearable alerts |
| Publish | `mm/fixed/+/result` | Gateway classification |
| Publish | `mm/fixed/+/status` | Forwarded wearable presence |
| Publish | `mm/fixed/+/command_ack` | Forwarded acknowledgements |
| Publish | `mm/fixed/+/telemetry` | Allowed; ingestion waits for the on-demand start/stop design |
| Publish | `mm/gateway/{own CN}/#` | `ids_event`, `status`, `backlog` |
| Subscribe | `mm/fixed/+/command` | Commands for its wearables |
| Everything else | — | Denied |

Observe-only: any active gateway may forward for any wearable; the cloud records `current_gateway_id`. Enforcing a pre-assigned wearable↔gateway mapping stays open (`gaps.md`).

Implemented in Slice 4 by the API's authorisation hook: the wearable level must be a canonical UUID; a subscription may name one wearable instead of `+`; the gateway must still be an active `fixed_gateway`. A denied publish or subscription gets MQTT 5 reason code 0x87 and the connection stays up (`deny_action = ignore`). EMQX caches authorisation results for 1 minute (its default), so a suspended or revoked gateway that stays connected loses topic access within a minute; a revoked credential alone takes effect at the next connect (`gaps.md`).

## D6 — Fixed-path alert payload v1 (Decided; shared with the firmware; Implemented 2026-10-29)

Schema file: `shared/contracts/alert-payload-v1.schema.json`, generated from `cloud/backend/app/contracts.py`.

```json
{
  "v": 1,
  "msg_id": "6f1c2e0a-…",
  "seq": 1842,
  "type": "alert",
  "fs_hz": 360,
  "lead": "MLII",
  "n_samples": 1080,
  "encoding": "int16le-base64",
  "samples": "AAEAAgAD…",
  "screening": { "label": "abnormal", "confidence": 0.93, "model": "tinydl-0.1" },
  "segment_start": "2026-11-02T10:15:03.120Z",
  "sent_at": "2026-11-02T10:15:06.500Z"
}
```

- `msg_id` (UUID) makes a QoS 1 redelivery idempotent; `seq` is a per-device counter that shows gaps.
- `device_id` is not in the payload: it comes from the topic, which the gateway's ACL and D1 cover.
- `sent_at` is benchmark-only and never used in a security decision. `fs_hz` 360 is an example; the sampling rate is still open.
- Implemented (Slice 5): unknown fields are refused, so a change is a new `v`; `samples` must decode to exactly `2 × n_samples` bytes; `n_samples` is at most 65 536; times must carry a zone, and `segment_start` may lead the broker's clock by at most 5 minutes; `screening` is required (the alert exists because TinyDL flagged it). `sent_at` is optional.

## D7 — Normalised ingestion message `ingest-v1` (Decided; Implemented 2026-10-29)

Schema file: `shared/contracts/ingest-v1.schema.json`, generated from `cloud/backend/app/contracts.py`. The only contract the ingestion API accepts; a new protocol means a new adapter producing it.

```json
{
  "device_id": "<wearable uuid>",
  "device_type": "wearable",
  "auth_method": "x509_mtls",
  "attested_by": "<gateway uuid>",
  "authenticated": true,
  "auth_metadata": { "listener": "gw-mtls" },
  "msg_type": "alert",
  "received_at": "…",
  "hops": { "sent_at": "…", "broker_at": "…", "adapter_at": "…" },
  "payload": { }
}
```

`attested_by` is null on the mobile path. `auth_metadata` is benchmark/debug only; no logic may depend on its shape.

Implemented (Slice 5): `POST /internal/ingest`, called only by the adapter with `INGEST_SECRET`, not in the API description. The API validates the envelope and the payload for its `msg_type` again, though the adapter already has. A wearable sends `alert` and `status`; a gateway sends `status` and `ids_event`. Messages with no attesting gateway are rejected until the mobile path has an adapter. The hop times are stored in `ingested_messages` (D15).

## D8 — Database access (Decided)

SQLAlchemy 2 Core (no ORM models), Alembic migrations, psycopg 3.

## D9 — Role × endpoint matrix (Decided)

✔ allowed, ✘ denied. Implemented as one parametrised test (TC-C09, `cloud/backend/tests/integration/test_access.py`), which also fails if an endpoint of the app has no row. A role denied an endpoint gets 403; an allowed role asking for a patient outside its reach (another organisation, or for a doctor a patient who is not theirs) gets 404, as for a patient that does not exist.

| Endpoint group | System admin | Org admin | Doctor | Patient |
|---|---|---|---|---|
| Organisations: create, suspend, list all | ✔ | ✘ | ✘ | ✘ |
| Organisation admin accounts: create | ✔ | ✘ | ✘ | ✘ |
| Own organisation: read | — | ✔ | ✔ | ✔ |
| Patients: list | ✘ | ✔ (own org) | ✔ (own patients) | ✘ |
| Devices, credentials: register, suspend, revoke | ✔ | ✘ | ✘ | ✘ |
| Device grants to organisations | ✔ | ✘ | ✘ | ✘ |
| Devices of own organisation: list, live status | ✔ (all) | ✔ | ✔ (own patients' devices) | ✘ |
| Doctor/patient accounts: create, disable | ✘ | ✔ (own org) | ✘ | ✘ |
| Issue a wearable to a patient | ✘ | ✔ | ✘ | ✘ |
| Assign a doctor to a patient | ✘ | ✔ | ✘ | ✘ |
| Patient disorders: record | ✘ | ✔ | ✘ | ✘ |
| Patient disorders: read | ✘ | ✔ | ✔ (own patients) | ✘ |
| Export a patient | ✘ | ✔ | ✘ | ✘ |
| Patient ECG, classifications, alerts: read | ✘ | ✘ | ✔ (own patients) | ✔ (self) |
| Acknowledge an alert | ✘ | ✘ | ✔ (own patients) | ✘ |
| Request on-demand ECG | ✘ | ✘ | ✔ (own patients) | ✘ |
| Security events, attack tests | ✔ | ✘ | ✘ | ✘ |
| Audit log (grants, issues, exports) | ✔ (device side) | ✔ (own org) | ✘ | ✘ |
| Directory: names of the people one works with (D14) | ✘ | ✔ (own org, with e-mail) | ✔ (self, own patients) | ✔ (self, own doctor) |

- The organisation admin **cannot read patient ECG data**, classifications or alerts.
- Open: how a patient export works when the org admin cannot read ECG (whether the export bundle includes ECG, produced by the API without the org admin viewing it). Until decided, `POST /patients/{id}/exports` returns the pseudonym, disorders, care and wearable history with `ecg_included: false`, and logs the export.
- Rows "Organisation admin accounts" and "Patients: list" were added on 2026-10-24 while building Slice 3; "Directory" on 2026-10-25 for the dashboard (D14). Not implemented yet: on-demand ECG (start/stop design open) and attack tests (Iteration 5); their rows are tested when the endpoints exist.

Endpoints (2026-10-25):

| Endpoint group | Endpoints |
|---|---|
| Registry (system admin) | `/admin/organisations[/{id}[/admins]]`, `/admin/devices/...`, `/admin/credentials/{id}/revoke`, `/admin/grants/{id}/revoke`, `GET /admin/audit`, `GET /admin/security-events` |
| Own organisation, devices | `GET /organisation`, `GET /devices` (org admin: granted devices; doctor: their patients' wearables) |
| Accounts (org admin) | `GET/POST /accounts`, `POST /accounts/{user_id}/disable` |
| Patients | `GET /patients`, `PUT /patients/{id}/doctor`, `POST/DELETE /patients/{id}/wearable`, `GET/POST /patients/{id}/disorders`, `POST /patients/{id}/exports` |
| ECG and alerts (doctor, patient) | `GET /alerts`, `GET /patients/{id}/alerts`, `POST /alerts/{id}/acknowledge`, `GET /patients/{id}/segments`, `GET /segments/{id}` |
| Audit (org admin) | `GET /audit` |
| Directory (D14) | `GET /directory` |
| Public | `GET /livez`, `GET /healthz`, `GET /auth/config` (the dashboard's sign-in settings) |

## D10 — EMQX 6.3.2, pinned (Decided)

- Image `emqx/emqx:6.3.2` (released 2026-10-16; amd64 and arm64 builds, so the same image runs on the cloud Pi). Pin this exact tag in `compose.yaml`; upgrades are deliberate and get a change-log entry.
- Licence: Business Source License 1.1 (EMQX 5.9.0 and later). Its Additional Use Grant allows production use of a single node, and unrestricted non-profit use by accredited academic institutions. A single cloud node for this FYP is covered. Each version converts to Apache 2.0 four years after its release.
- Features this design relies on, confirmed in the EMQX docs: `mqtt.peer_cert_as_username = "cn"`; HTTP authentication with `allow`/`deny`/`ignore` results; rule-engine Republish whose templates reference fields from the rule SQL. Exact v6 configuration syntax is verified in Slice 4.

## D11 — Audit log table (Decided 2026-10-24)

The report's tables record who granted, issued, assigned and exported (`granted_by`, `issued_by`, `assigned_by`, `exported_by`), but not who created or disabled an account, returned a wearable or ended an assignment. A separate append-only table records every registry and organisation action in the same transaction as the action:

```
audit_log: event_id, at, actor_id → users, scope (registry | organisation), org_id, action, target_id, details jsonb
```

- `scope = registry`: system-admin actions (organisations, organisation admins, devices, credentials, grants). `GET /admin/audit` shows only these, so the system admin sees no patient or doctor ids (TC-C11).
- An organisation admin sees every event of their own organisation (`GET /audit`), including the registry events about it (its device grants, its admins).
- `mm_api` has `INSERT` and `SELECT` only on `audit_log`; it cannot change or delete an entry (TC-C03).
- Rejected alternative: a view over the actor columns of the report's tables (would miss account and return events, and cannot record who ended something).

## D12 — The API's ZITADEL service account; accounts start with an invite code (Decided 2026-10-24)

```
zitadel-bootstrap (IAM_OWNER token, bootstrap volume only)
   └─ creates machine user mm-api, instance role IAM_ORG_MANAGER
      └─ writes its token to the mm-secrets volume ─────► api (read-only mount)

API (as mm-api)                                     ZITADEL
 POST /admin/organisations ─────────────────────────► create organisation; grant project (org_admin, doctor, patient)
 POST /admin/organisations/{id}/admins, POST /accounts ► create human user (e-mail as username), user grant with
                                                        the role, invite code returned (no e-mail sent)
 POST /accounts/{id}/disable ───────────────────────► deactivate user
```

- `IAM_ORG_MANAGER` lets the API manage organisations, their users and user grants and project grants, but not instance settings, instance members or the project's roles. The bootstrap service account (`IAM_OWNER`) stays out of the API's reach.
- The token lasts a year. The bootstrap job checks it on every `up` and replaces it (deleting the account's old tokens) when it is missing or no longer works. The API starts after the job and reloads the file when ZITADEL refuses the token it holds.
- ZITADEL is changed first (`users.zitadel_sub` needs its id). If a later ZITADEL step or the database insert fails, the ZITADEL user or organisation is deleted again. Anything left behind is inert: the API refuses ZITADEL users it has not registered.
- No password is set by the API. The invite code is returned once, to the admin who created the account, who hands it to the person; the person then sets their own password or passkey in ZITADEL's login. The dashboard's invite page explains it, and the dashboard's API-mode browser tests redeem codes in ZITADEL's login (TC-D05).
- Names and e-mail addresses live only in ZITADEL; the database keeps the role, organisation and, for patients, the pseudonym.

## D13 — EMQX configuration and the internal service listener (Decided 2026-10-24)

```
emqx (image built from cloud/emqx/)
├── ssl:gateway  8883  mTLS, zone gateway (username = cert CN), authn → API /internal/emqx/authn/gateway
├── tcp:internal 1883  password, authn → API /internal/emqx/authn/service   (adapter: mm-adapter)
├── authorization: HTTP → API /internal/emqx/authz, no_match = deny
├── rule mm_ingest: mm/fixed/#, mm/gateway/# → ingest/{username}/{topic}
└── defaults (tcp 1883, ssl 8883 with demo certs, ws, wss) disabled
```

- The configuration is `etc/emqx.conf`, which takes precedence over dashboard changes, so nothing can be loosened at runtime. EMQX 6 does not substitute environment variables in it (verified), so `mm-entrypoint.sh` renders it from a template at start with the hook secret and the Erlang cookie (both from `.env`, alphanumeric only).
- The cloud server certificate (`mmca issue cloud`) is streamed into the `emqx-certs` volume by `cloud/scripts/install-emqx-certs.sh` (no bind mount). Without it EMQX starts with the gateway listener off and a warning.
- Published ports: 8883 on `EMQX_GATEWAY_BIND_ADDRESS` (127.0.0.1 on the laptop, the Tailscale address on the cloud Pi), 1883 on 127.0.0.1 only.
- Rejected alternative: per-listener built-in password database for the adapter (would need a credentials file baked into the image or a bind mount).

## D14 — Dashboard sign-in, CORS and the name directory (Decided 2026-10-25)

```
browser (web/dashboard) ── GET /auth/config ─────────────────► api   {issuer, client_id, project_id, scope}
        │ authorization code + PKCE (no secret)
        ▼
ZITADEL app "MedMusketeer Dashboard" (created by zitadel-bootstrap)
        │ JWT access token: project audience, roles, resource owner
        ▼
browser ── Authorization: Bearer … (CORS: DASHBOARD_ORIGINS) ──► api   /me, /directory, …
```

- **The dashboard's OIDC app** is created by the `zitadel-bootstrap` job in the MedMusketeer project: a user-agent app with the authorization-code grant, PKCE and no client secret, refresh tokens allowed, and **JWT access tokens with the roles asserted** (the API validates JWTs only). Its redirect URI is `{origin}/auth/callback` and its post-logout URI `{origin}/` for every origin in `DASHBOARD_ORIGINS` (default `http://localhost:3000`). The job brings it in line with that setting on every `up`. Dev mode (which allows http redirect URIs) relaxes redirect checks for the whole app, so the origins must be all http (a development stack, dev mode on) or all https (dev mode off); the job refuses a mix, which would let a production app send codes to `http://localhost`.
- **`GET /auth/config`** (public) returns the issuer, the app's client id, the project id and the scopes a login must request (`openid profile email offline_access`, the project audience, the project roles and the resource owner). The dashboard reads it at start, so the same build works against any stack. The client id is written to `zitadel.json` as `dashboard_client_id`; without it the endpoint answers 503.
- **CORS**: the API sends CORS headers only to the origins in `MM_CORS_ORIGINS` (compose sets it from `DASHBOARD_ORIGINS`), for GET/POST/PUT/PATCH/DELETE with the `Authorization` and `Content-Type` headers, and without credentials: the dashboard sends a bearer token, never cookies. With no origins configured, no CORS headers are sent.
- **`GET /directory`** returns `{user_id, role, status, given_name, family_name, email}` for the accounts the caller works with. The names are read from ZITADEL as `mm-api` (one list call per 100 users) and reused for 60 seconds.
  - Organisation admin: every account of the organisation, with e-mail, since they manage the accounts.
  - Doctor: themselves and their current patients, without e-mail. A doctor identifies the patients they treat by name; ECG data stays filed under the pseudonym.
  - Patient: themselves and their current doctor, without e-mail.
  - System admin: no directory (403). They see no patient or doctor data (D9).
  - An account ZITADEL returns no profile for is listed with empty names. A ZITADEL failure answers 502.
- **Development data**: `python -m app.manage seed-dev` creates, on an empty stack, a system admin and the organisation "Dev Hospital" with an org admin, two doctors and three patients. All of them are ZITADEL human users with one printed password. It also adds a gateway and wearables, alert segments of synthetic ECG with classifications and alerts, and IDS events. The ECG is generated and has no clinical meaning. It exists so that the dashboard can be built and tested before ingestion (Slice 5).
- Rejected alternatives:
  - The dashboard reading names from ZITADEL itself: a user's token cannot read other users.
  - A name column in `users`: names would then live in two places (D12 keeps them in ZITADEL).
  - A same-origin reverse proxy instead of CORS: the dashboard was to be hosted on Vercel, the API on the cloud Pi. **Revisit (2026-10-26):** the dashboard will now be served from the cloud Pi, so it could share the API's origin through the stack's proxy and CORS would not be needed. To be decided with the Pi deployment (`docs/iterations/iteration-6-dashboard.md`, Deployment).

## D15 — Ingestion: presence and IDS payloads, idempotency, liveness (Decided 2026-10-29)

```
gateway ──mm/fixed/{w}/alert|status, mm/gateway/{gw}/status|ids_event──► EMQX
                           rule mm_ingest ──► ingest/{gw}/{topic}                 ┐
EMQX connect/disconnect ── rule mm_presence ──► ingest/{gw}/broker/client.(dis)connected ┤
                                                                                  ▼
adapter (python -m app.adapter, mm-adapter, persistent session, manual ack)
   validates against shared/contracts, builds ingest-v1 ──► POST /internal/ingest (INGEST_SECRET)
   ack after the API answered; retries while it cannot                            │
                                                                                  ▼
API: registry checks ─► one transaction: session, segment, chunk, classification, alert, NOTIFY mm_alerts
                                         security_events | devices presence | ingested_messages
```

- **Payload contracts** (`shared/contracts/`, generated from `app/contracts.py`; a unit test fails if the files are stale):
  - `status-v1` `{"v": 1, "state": "online" | "offline", "reason"?, "sent_at"?}`: a gateway forwards each wearable's presence on `mm/fixed/{w}/status` and reports its own on `mm/gateway/{gw}/status`. `reason: "mode_switch"` before the wearable changes path (ADR-5).
  - `ids-event-v1` `{"v": 1, "msg_id", "ts", "device_id"?, "mode": "ids" | "ips", "predicted_class", "outcome", "action"?, "action_result"?}` on `mm/gateway/{gw}/ids_event`. In IDS mode `action` and `action_result` must be absent. `device_id`, if given, must be a registered device. The event is stored with `event_id = msg_id` and `gateway_id` = the attesting gateway, never a payload field.
  - Not ingested yet, logged and skipped by the adapter: `telemetry` (start/stop design open), `result` (the gateway classifier, Iteration 4), `command_ack` (no commands yet), `backlog` (outage upload, IPS methodology).
- **The adapter** is a module of the backend package and runs from the API image as the compose service `adapter`. Topics map as in its docstring; `attested_by` is the gateway id from the topic, which is the broker's username (D1). It connects with a persistent session (`clean_start` off, 24 h expiry) and acknowledges a message only after the API has answered, so EMQX keeps QoS 1 messages while the adapter or the API is down. One worker thread posts in arrival order and retries the same message with backoff (1 to 30 s) on a network error or a non-422 answer. A 422 (rejected) or a contract failure is logged and dropped.
- **Registry checks before any write** (each rejection logged by the API with its reason; the transaction is rolled back):
  - the attesting gateway is an active `fixed_gateway`, and a gateway reports only for itself. A gateway's own offline report counts even if it is suspended, so its wearables do not stay on its path;
  - the wearable is registered as a wearable and active;
  - for an alert, the wearable has an open assignment to a patient of the organisation it is granted to (the assignment and grant rows are locked, so a concurrent return or grant revoke either ends first or waits).
- **Idempotency:** `ingested_messages (device_id, msg_id)` (migration 0003), scoped to the device so that one device cannot pre-empt another's ids. A redelivered alert or IDS event answers `duplicate` and writes nothing. Status messages carry no `msg_id`; applying one twice has the same effect as once. `mm_api` may only insert into the table.
- **An alert** opens or continues the wearable's monitoring session for that patient, organisation and path. An open session for anything else is ended first, so a session never collects another patient's data, even if an assignment change missed it. It writes:
  - the segment (`kind = alert`, the lead in the new `ecg_segments.lead`);
  - one chunk with all samples (`seq` 0), with `attested_by` and `auth_method`;
  - the wearable's screening as a classification (`source = wearable`);
  - the alert, with `origin = wearable` and `severity = unrated`.
  
  Then it sends `NOTIFY mm_alerts` with the alert, patient and device ids; this is delivered on commit. The device `seq` is kept in `ingested_messages`, not as the chunk's `seq`.
- **Severity** is `unrated`: the wearable's screening gives a label and a confidence, not a severity, and inventing a mapping would be a clinical decision. The gateway or cloud classifier is to rate it (open, `gaps.md`).
- **Liveness** (`stack.md`, "Device presence/liveness detection"), all times the broker's:
  - every message refreshes the attesting gateway's `last_seen`; a wearable's alert or `online` status sets its `last_seen`, `current_mode = fixed` and `current_gateway_id`;
  - a wearable reported `offline` becomes `current_mode = unknown` with no gateway, and its `last_seen` stays (nothing was heard from it);
  - a gateway that goes offline (its own status, or EMQX's disconnect event through the rule `mm_presence`) turns its `fixed` wearables `unknown`, keeping `current_gateway_id`;
  - an offline report older than the device's `last_seen` is stale and ignored. Online reports are applied in arrival order; per-topic MQTT ordering makes reordering rare, and the next message corrects it;
  - the dashboard never shows "offline" (Iteration 6), which matches: `unknown` is what the cloud can say.
- **The broker's connection events** come from the rule `mm_presence` on `$events/client_connected` and `$events/client_disconnected` (everyone but `mm-adapter`), republished to `ingest/{username}/broker/{event}`. Gateways cannot publish under `ingest/` (D5), so these cannot be forged. Gateway LWTs are therefore not needed for liveness; a gateway may still send them as status.
- **Alert push:** only `NOTIFY` is built. The WebSocket endpoint (a stretch goal) is not, because the dashboard polls alerts every 15 s (Iteration 6).
- Rejected alternatives:
  - The adapter writing to the database itself: it would bypass the single ingest-v1 contract of D7.
  - Idempotency by a `msg_id` column on `ecg_segments`: it would not cover IDS events or later message types.
  - Relying on gateway LWTs for gateway liveness: a clean disconnect sends none, and a gateway without one would never go `unknown`.

