# Message contracts

JSON Schemas (draft 2020-12) of the messages between devices and the cloud. They are generated from the models in `cloud/backend/app/contracts.py`, which the cloud's adapter and ingestion API validate with. Do not edit the files by hand: change the models and run

```bash
cd cloud/backend && .venv/bin/python -m app.contracts
```

A unit test (`tests/unit/test_contracts.py`) fails while a file differs from its model.

| File | Topic | Sent by | Decision |
|---|---|---|---|
| `alert-payload-v1.schema.json` | `mm/fixed/{wearable}/alert` | Wearable (forwarded by its gateway) | `docs/decisions/cloud-backend.md` D6 |
| `status-v1.schema.json` | `mm/fixed/{wearable}/status`, `mm/gateway/{gateway}/status` | Gateway: the wearable's presence, and its own | D15 |
| `ids-event-v1.schema.json` | `mm/gateway/{gateway}/ids_event` | Gateway IDS/IPS | D15 |
| `ingest-v1.schema.json` | (HTTP, `POST /internal/ingest`) | The cloud's MQTT adapter, to the ingestion API | D7 |

Rules shared by every payload:
- Unknown fields are refused. A change is a new version, with a new `v` and a new file.
- Times are RFC 3339 with a zone, for example `2026-11-02T10:15:03.120Z`.
- The sending device is never named in the payload. It comes from the topic and, for the gateway, from the broker (D1).
- `sent_at` is for the latency benchmark only and is never used in a security decision.

`samples` in an alert is `n_samples` little-endian signed 16-bit values, Base64 with padding. The schema cannot express this check, but the cloud makes it: the samples must decode to exactly `2 × n_samples` bytes.
