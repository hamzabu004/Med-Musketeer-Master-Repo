# Cloud ingestion: the MQTT adapter, the ingestion API and the message contracts (Iteration 3, Slice 5)

- **Date:** 2026-10-29
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/ shared/`

## What changed
- **Contracts** (`shared/contracts/`): JSON Schemas generated from `cloud/backend/app/contracts.py`:
  - `alert-payload-v1` (D6);
  - `ingest-v1` (D7);
  - `status-v1` and `ids-event-v1` (new, D15).

  Unknown fields are refused, and a unit test fails when a file is stale.
- **Adapter** (`app/adapter.py`, compose service `adapter`, from the API image): subscribes to `ingest/#` as `mm-adapter`. It takes `attested_by` from the topic (the broker's username, D1), validates each payload, and posts ingest-v1 to the API. Delivery is at least once: it keeps a persistent session, acknowledges a message only after the API has answered, and retries in order while the API is unreachable. `telemetry`, `result`, `command_ack` and `backlog` are skipped.
- **Ingestion API** (`POST /internal/ingest`, `app/ingest.py`, new secret `INGEST_SECRET`): registry checks come first: an active attesting gateway; an active wearable; and, for an alert, an issued wearable granted to the patient's organisation. Then, in one transaction, an alert writes:
  - the session;
  - the segment (with its lead);
  - the samples, with `attested_by`;
  - the wearable's screening as a classification;
  - the alert (`origin` wearable, `severity` unrated).

  It also sends `NOTIFY mm_alerts`. IDS events go to `security_events` under the publishing gateway. Rejections are logged with their reason.
- **Idempotency and latency record:** migration 0003 adds `ingested_messages`, keyed by `(device_id, msg_id)`, with the hop times. The API may only append to it. It also adds `ecg_segments.lead`, returned by `/segments`.
- **Liveness:** the EMQX rule `mm_presence` republishes each gateway's connect and disconnect, and the adapter turns them into the gateway's status. A gateway going offline, or a wearable reported offline, makes the wearable `unknown`, not offline. Stale offline reports are ignored.
- **Tests:** the shared gateway helpers moved to `tests/integration/stack.py`. The MQTT monitor in TC-C14/C17 now ignores the broker's connection events. `paho-mqtt` is now a runtime dependency (lock regenerated; only it was added).
- **Test IDs:** Slice 5's planned TC-C19 to TC-C24 became TC-C20 to TC-C25, because TC-C19 went to the dashboard sign-in on 2026-10-25. The gateway-down case got TC-C26, and the Pi smoke test is now TC-C27.
- **Docs:** D15 recorded in `cloud-backend.md`; D6 and D7 marked implemented. Also updated: `iteration-3-cloud.md`, `stack.md` (liveness), `gaps.md`, `mqtt-fixed-path-topics.md`, `test_traceability.md`, `cloud/README.md`.

## Why
- Slice 5 of `docs/iterations/iteration-3-cloud.md`: exit criterion 4 needs an alert from a gateway to land in the database with the right patient and `attested_by`, and an alert for an unissued wearable to be rejected and logged.
- The firmware has no status payload or LWT yet, and the gateway uplink is not built, so the cloud defines `status-v1` and `ids-event-v1` now for Iteration 4 to adopt.
- Severity is left `unrated`: deriving it from the screening confidence would be a clinical decision nobody has taken (`gaps.md`).

## Evidence
375 cloud tests pass (`docs/testing/evidence/2026-10-29/cloud/`; unit tests, the rest against a database container or the full stack, which now has 7 healthy services). End to end through EMQX and the adapter:
- TC-C20 and TC-C22: a gateway's alert, published twice, is stored once, with the publishing gateway as `attested_by`;
- TC-C21 and TC-C23: an unissued wearable's alert is rejected and logged by the API, and malformed payloads are dropped and logged by the adapter;
- TC-C24: an IDS event is stored under its gateway;
- TC-C26: a gateway's disconnect turns its wearable `unknown`;
- an alert published while the adapter was stopped was stored once it restarted.

At the API, with the database, there are further cases for each registry rule, plus TC-C25 (reassigning a wearable). Record in `stack/tc_c20_c26_ingestion.json`. Line coverage: `ingest.py` 97 %, `contracts.py` 94 %, `adapter.py` 77 % (its MQTT callbacks run only in the container).
