# MedMusketeer — Cloud Backend Design (Iteration 3)

Companion to `stack.md`. Records decisions D1 to D10 from Slice 0 of `docs/iterations/iteration-3-cloud.md`. Status markers follow `stack.md`. All ten are **Decided** (2026-10-23). Details marked "verify in Slice N" are to be confirmed against the pinned versions while building.

Last updated: 2026-10-23

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
- Verify in Slice 4: the republish topic template with `${username}` and `${topic}` from the rule SQL.

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
  urn:zitadel:iam:org:project:roles            → role
  urn:zitadel:iam:user:resourceowner:id        → ZITADEL org id → organisations.org_id
```

```
Postgres (mirror)
organisations: org_id, name, kind, status, zitadel_org_id   ← column added to the report's schema
users:         user_id, zitadel_sub, role, org_id           ← mirror for joins; changed only by the API
```

- ZITADEL is the source of truth for the role. The API authorises from the token's role and takes `org_id` from `organisations`.
- The API is the only path that changes a role: it updates ZITADEL and the `users` row in one operation.
- Verify in Slice 3: the claim names, and the project-grant-per-organisation set-up.

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

## D6 — Fixed-path alert payload v1 (Decided; shared with the firmware)

Schema file: `shared/contracts/alert-payload-v1.schema.json` (written in Slice 5, shared with the Iteration 2 firmware work before then).

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

## D7 — Normalised ingestion message `ingest-v1` (Decided)

Schema file: `shared/contracts/ingest-v1.schema.json`. The only contract the ingestion API accepts; a new protocol means a new adapter producing it.

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

## D8 — Database access (Decided)

SQLAlchemy 2 Core (no ORM models), Alembic migrations, psycopg 3.

## D9 — Role × endpoint matrix (Decided)

✔ allowed, ✘ denied. Implemented as one parametrised test (TC-C09).

| Endpoint group | System admin | Org admin | Doctor | Patient |
|---|---|---|---|---|
| Organisations: create, suspend, list all | ✔ | ✘ | ✘ | ✘ |
| Own organisation: read | — | ✔ | ✔ | ✔ |
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

- The organisation admin **cannot read patient ECG data**, classifications or alerts.
- Open: how a patient export works when the org admin cannot read ECG (whether the export bundle includes ECG, produced by the API without the org admin viewing it).

## D10 — EMQX 6.3.2, pinned (Decided)

- Image `emqx/emqx:6.3.2` (released 2026-10-16; amd64 and arm64 builds, so the same image runs on the cloud Pi). Pin this exact tag in `compose.yaml`; upgrades are deliberate and get a change-log entry.
- Licence: Business Source License 1.1 (EMQX 5.9.0 and later). Its Additional Use Grant allows production use of a single node, and unrestricted non-profit use by accredited academic institutions. A single cloud node for this FYP is covered. Each version converts to Apache 2.0 four years after its release.
- Features this design relies on, confirmed in the EMQX docs: `mqtt.peer_cert_as_username = "cn"`; HTTP authentication with `allow`/`deny`/`ignore` results; rule-engine Republish whose templates reference fields from the rule SQL. Exact v6 configuration syntax is verified in Slice 4.
