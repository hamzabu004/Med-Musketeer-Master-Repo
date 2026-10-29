---
name: medmusketeer-gaps
description: Open architecture gaps for MedMusketeer, identified but not yet resolved. Companion to medmusketeer-fyp (scope.md) and medmusketeer-stack (stack.md) — this file tracks what's still undecided/unbuilt. Consult when planning next work items or checking whether something assumed "figured out" is actually still open.
---

# MedMusketeer — Known Architecture Gaps

This file is a **gap tracker**, not a decision record. Items move out of this file and into `stack.md` (or get flagged against `scope.md` if they imply a scope question) once actually decided. Don't treat anything listed here as resolved just because it's written down. The mid report's own list is in §5 "Design items still to be settled"; this file is the wider working list.

Last updated: 2026-10-29

## Identity, crypto, provisioning
- **Revocation on the gateway:** decided (push + cache, `stack.md`, `cloud-backend.md` D16), not built; planned in `docs/iterations/iteration-4-revocation-sync.md`. The gateway's Mosquitto cannot disconnect a revoked wearable (only refuse its messages) or enforce the revocation of a single credential of an active wearable (Slice 0 spike); both accepted. The CA tool has no `revoke` command (removed 2026-10-29): revocation goes through the registry API
- **CN/SAN pinning, remaining sides:** the wearable's role-name pin of the gateway is implemented. Still to do: confirm the ESP32-S3 `common_name` check does a literal match for UUID-style names; the gateway's outbound check of the cloud identity; the cloud-side checks
- **Mobile-path envelope wire format:** construction is Proposed in `stack.md`; field widths, counter-window size, persist-ahead reservation block size and `key_epoch` handling are open
- **Envelope keys and the cloud envelope certificate** are not issued by the CA tool yet (the cloud TLS server certificate is, since 2026-10-24)
- **The existing MedMusketeer CA has no key identifiers.** CAs made by `mmca` before 2026-10-24 have no Subject Key Identifier, so strict X.509 verifiers (Python 3.13+'s default TLS context, which the gateway's uplink uses) refuse every chain from them. Decided 2026-10-29: replace the CA and re-issue the gateway, the wearable and the cloud certificate (steps in `iteration-4-revocation-sync.md`, Slice 0). Not carried out yet; needed before the uplink (Iteration 4)
- **Revoking a credential does not disconnect a live gateway**: it is refused at its next connect. Suspending or revoking the device also removes its topic access within EMQX's 1-minute authorisation cache. Disconnecting at once through EMQX's REST API (D4 "may") is not built; planned with D16 (Iteration 4, Slice 1)
- **Credential rotation trigger:** manual rotation accepted for FYP-1, but the trigger condition (schedule vs on-suspicion) is undefined

## Mobile relay app
- **Phone-to-patient/wearable binding auth** — unspecified how a specific phone install is tied to a specific patient/wearable pairing, so a random phone install can't relay for someone else's wearable. This is a real security gap, not just a missing nice-to-have.
- Relay app not started (stack decided: native Android, Kotlin + Jetpack Compose)
- BLE relay details: chunk header layout, MTU target, wearable buffer size, separate indicate characteristic for alerts

## Device registry / data model (blocks Iteration 3)
- The schema is **designed** (mid report §5, summarised in `stack.md`) but not implemented; column-level details are still open
- `status`/`last_seen`/`current_mode` on the mobile path (envelope arrival) and how it reconciles with the fixed path. The fixed path is implemented (`cloud-backend.md` D15): broker connect/disconnect events and gateway-forwarded wearable status, offline shown as `unknown`
- Heartbeat envelope interval/timeout thresholds for mobile-path liveness
- Raw ECG retention period (only `ecg_chunks` are dropped; the migration uses a 90-day placeholder)
- Cloud data at rest: disk encryption of the cloud server and least-privilege database roles (planned with the cloud platform)
- EMQX starts before the API, so its HTTP authenticators are briefly down at start; gateways connecting then are refused and must retry (they do, with MQTT reconnect)

## Ingestion / messaging (blocks Iteration 3–4)
- ~~The adapter's code-level interface~~ — resolved 2026-10-29: `cloud-backend.md` D15 (adapter, ingestion API, status and IDS-event payloads, idempotency)
- `alerts.severity` is unused (nullable, empty, not in the API): alerts carry the wearable's label and confidence only (`cloud-backend.md` D15). Drop the column, or give it a meaning, if a later classifier needs one
- Ingestion of `result` (gateway classification of an alert's segment), `command_ack` and `backlog` (post-outage upload): payloads not defined; the adapter skips them
- The WebSocket alert push: `NOTIFY mm_alerts` is sent, nothing listens yet (the dashboard polls)
- Growth of `ingested_messages` (one row per alert and IDS event, no retention policy yet)
- Telemetry QoS and the recording payload (the alert payload v1 is decided in `cloud-backend.md` D6); how an on-demand stream starts and stops (the request command, duration or explicit stop, and the `command_ack`)
- Enforcing wearable↔gateway assignment (observe-only decided for Iteration 3, `cloud-backend.md` D5); the gateway's local wearable allowlist
- How a patient export works when the organisation admin cannot read ECG data (`cloud-backend.md` D9); until decided, exports leave ECG out (`ecg_included: false`)
- Mode-switch behaviour: buffered data on a switch, persistence across reboot, button handling

## ECG / model layer
- **TinyDL on-device screening model** has no architectural spec. Because only screening-flagged alerts leave the wearable (ADR-1), this blocks the whole alert pipeline and the path benchmark, and its recall limits the whole system
- Model choice: the base-paper method (LightGBM, 72–77% patient-level) is dropped; the teacher/student candidates (classical ML search; 1D-CNN, RNN, LSTM, KAN-Former) are being evaluated in Iteration 2; no teacher has reached the 95% lock threshold yet
- Signal preprocessing: sampling rate (MIT-BIH is 360 Hz), window length, input unit (samples, beats or seconds), filtering and segmentation
- Whether the gateway multiclass model and the cloud multiclass model (mobile path) are the same model redeployed or separately tuned for different compute budgets
- **Hardware:** the ADS1292 digital front end has been requested from the lab and not received; the firmware sampling path must be re-checked against it on arrival. Until then only the AD8232 (testing only)

## IDS/IPS
- Final model not chosen (offline Random Forest and XGBoost baselines on CICIoMT2024 exist); next steps listed in the mid report §10 (confusion analysis, realistic class distribution, leakage checks)
- Gateway feature extraction: reproducing the 45 CICIoMT2024 features from the gateway's own capture pipeline
- IPS action mechanism: iptables? application-layer rate limiting? which layer on the RPi actually implements "reject/throttle"
- Gateway outage-buffer and security-event store (marked TBD in the report)

## Dashboard
- ~~No screen-level spec for the new dashboard~~ — resolved 2026-10-26: `docs/iterations/iteration-6-dashboard.md` (all four roles built and tested on the cloud API)
- Dashboard deployment on the cloud Pi (with the cloud's Slice 6 and the public domain); whether it shares the API's origin through the proxy, which would make CORS unnecessary (`cloud-backend.md` D14)
- Cloud endpoints the dashboard works around: a single alert (`GET /alerts/{id}`), an organisation's admins for the system admin, grants by organisation, a single patient and an audit filter by target for the org admin, and paging past 1000 rows (audit, security events, alerts). Details: the iteration doc, "Waiting for the cloud"
- The ECG gain (ADC counts per mV) is not stored with segments; the dashboard assumes 200 counts/mV (MIT-BIH) and says so on every strip
- ZITADEL's login offers "Register new user": a self-registered user has no role and gets "no access". Decide whether the bootstrap turns self-registration off
- Alert escalation flow: `alerts.acknowledged_by` exists, but what happens when an alert is not acknowledged is undefined

## Non-functional / ops
- NTP on the gateway hotspot (the wearable already retries SNTP before MQTT; the benchmark methodology requires synchronised clocks on every hop)
- Buffer size/overflow policy for the wearable's "buffer unsent measurements" IPS behaviour, under real resource constraints
- No OTA/firmware update strategy (`device_updates` exists only if remote updates are adopted) — relevant if credentials ever need pushing to deployed devices
- Public-certificate operations: ACME client, automated renewal and EMQX reload, one domain/cert or separate subdomains
- No platform ops logging/monitoring (distinct from IDS/IPS event logging)
- ~~The invite-code onboarding is not tested past ZITADEL issuing the code~~ — resolved 2026-10-26: the dashboard's API-mode browser tests redeem codes in ZITADEL's login for a new org admin and a new patient (TC-D05)
- ~~The API returns no names~~ — resolved 2026-10-25: `GET /directory` reads them from ZITADEL (`cloud-backend.md` D14)
- ZITADEL's API and Login UI containers run as root (`user: "0"`, as in ZITADEL's reference compose) so they can share the bootstrap PAT file; drop root (e.g. a one-off step that chowns the `zitadel-bootstrap` volume) before the cloud is exposed beyond Tailscale
- `is_testbed` exists as a registry field, but physical/logical separation of testbed hardware from anything resembling real patient data isn't specified
- RSA key size (2048 assumed) and whether an RSA-CA variant is run for the key-type benchmark

## Resolved since the previous version (2026-09-26) — now in `stack.md`
- CSR/signing workflow → `mmca` on the custodian's build machine (Implemented)
- ESP32-S3 private key storage → plain flash in a read-only `creds` partition; secure boot/flash encryption excluded (accepted shortcut)
- Mobile app tech stack → native Android, Kotlin + Jetpack Compose
- BLE provisioning security → QR code + LE Secure Connections passkey shown on the OLED (Implemented)
- Fixed-path MQTT topic structure and ACLs → `mqtt-fixed-path-topics.md` (Implemented, container-verified)
- Postgres schema → designed (implementation still open, above)
- Role-based view definitions → four roles with defined responsibilities and access rules

## Suggested priority (highest leverage first)
1. TinyDL wearable model spec — blocks the alert pipeline and the path benchmark
2. Phone-to-patient/wearable binding auth — active security gap
3. On-demand recording start/stop — blocks `telemetry` ingestion
4. Mobile-path envelope wire format + remaining CN/SAN pinning — blocks the mobile path (Iteration 6)

(The Iteration 3 blockers — normalised message, `attested_by` source, role × endpoint matrix — were decided on 2026-10-23 in `cloud-backend.md`.)
