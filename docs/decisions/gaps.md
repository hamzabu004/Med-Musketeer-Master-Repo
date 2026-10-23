---
name: medmusketeer-gaps
description: Open architecture gaps for MedMusketeer, identified but not yet resolved. Companion to medmusketeer-fyp (scope.md) and medmusketeer-stack (stack.md) — this file tracks what's still undecided/unbuilt. Consult when planning next work items or checking whether something assumed "figured out" is actually still open.
---

# MedMusketeer — Known Architecture Gaps

This file is a **gap tracker**, not a decision record. Items move out of this file and into `stack.md` (or get flagged against `scope.md` if they imply a scope question) once actually decided. Don't treat anything listed here as resolved just because it's written down. The mid report's own list is in §5 "Design items still to be settled"; this file is the wider working list.

Last updated: 2026-10-23

## Identity, crypto, provisioning
- **Revocation:** `revoke` and the registry link are not built in the CA tool; whether fixed-path (wearable↔gateway) revocation is built in FYP-1 at all is undecided (candidate design in `stack.md`)
- **CN/SAN pinning, remaining sides:** the wearable's role-name pin of the gateway is implemented. Still to do: confirm the ESP32-S3 `common_name` check does a literal match for UUID-style names; the gateway's outbound check of the cloud identity; the cloud-side checks
- **Mobile-path envelope wire format:** construction is Proposed in `stack.md`; field widths, counter-window size, persist-ahead reservation block size and `key_epoch` handling are open
- **Envelope keys and cloud certificate profiles** are not issued by the CA tool yet
- **Credential rotation trigger:** manual rotation accepted for FYP-1, but the trigger condition (schedule vs on-suspicion) is undefined

## Mobile relay app
- **Phone-to-patient/wearable binding auth** — unspecified how a specific phone install is tied to a specific patient/wearable pairing, so a random phone install can't relay for someone else's wearable. This is a real security gap, not just a missing nice-to-have.
- Relay app not started (stack decided: native Android, Kotlin + Jetpack Compose)
- BLE relay details: chunk header layout, MTU target, wearable buffer size, separate indicate characteristic for alerts

## Device registry / data model (blocks Iteration 3)
- The schema is **designed** (mid report §5, summarised in `stack.md`) but not implemented; column-level details are still open
- `status`/`last_seen`/`current_mode` semantics per path (fixed = gateway-attested broker events; mobile = envelope arrival) and how the two reconcile
- Heartbeat envelope interval/timeout thresholds for mobile-path liveness
- Raw ECG retention period (only `ecg_chunks` are dropped)
- Cloud data at rest: disk encryption of the cloud server and least-privilege database roles (planned with the cloud platform)

## Ingestion / messaging (blocks Iteration 3–4)
- The adapter's code-level interface (the message `ingest-v1` and the `attested_by` source are decided in `cloud-backend.md` D1/D7)
- Telemetry QoS and the recording payload (the alert payload v1 is decided in `cloud-backend.md` D6); how an on-demand stream starts and stops (the request command, duration or explicit stop, and the `command_ack`)
- Enforcing wearable↔gateway assignment (observe-only decided for Iteration 3, `cloud-backend.md` D5); the gateway's local wearable allowlist
- How a patient export works when the organisation admin cannot read ECG data (`cloud-backend.md` D9)
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
- Role views are defined in the report (patient, doctor, organisation admin, system admin); no screen-level spec for the new dashboard yet (the POC-Lite docs cover the proof of concept)
- Alert escalation flow: `alerts.acknowledged_by` exists, but what happens when an alert is not acknowledged is undefined

## Non-functional / ops
- NTP on the gateway hotspot (the wearable already retries SNTP before MQTT; the benchmark methodology requires synchronised clocks on every hop)
- Buffer size/overflow policy for the wearable's "buffer unsent measurements" IPS behaviour, under real resource constraints
- No OTA/firmware update strategy (`device_updates` exists only if remote updates are adopted) — relevant if credentials ever need pushing to deployed devices
- Public-certificate operations: ACME client, automated renewal and EMQX reload, one domain/cert or separate subdomains
- No platform ops logging/monitoring (distinct from IDS/IPS event logging)
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
