---
name: medmusketeer-fyp
description: Locked project context for "MedMusketeer" — a Final Year Project (FYP) titled "Design and Development of a Secure Edge-Intelligent Cardiac Telemetry System for Remote Patient Monitoring." Use this skill whenever the user asks for help on this FYP, MedMusketeer, arrhythmia/ECG classification work, the IDS/IPS or gateway security components, the dashboard, timeline/milestones, or work division among the team — even if they don't name the project explicitly and just say things like "my FYP". Always consult this skill before writing code, slides, reports, or planning documents for this project, so scope, hardware, ownership and terminology stay consistent with the approved proposal. Do NOT let scope silently expand beyond what's listed here as "Committed" without the user explicitly asking to change scope.
---

# MedMusketeer — FYP Project Context

This file is the **scope lock** for one Final Year Project. It exists so that any LLM session working on this project (writing code, slides, reports, evaluation scripts, etc.) starts from the same facts instead of re-deriving or drifting from them. It defines *what the project is*. How it is built is in `stack.md`; what is still undecided is in `gaps.md`; progress and measured results are in the mid report and `docs/testing/` (see `README.md` in this folder).

**Source of truth**: the FYP-1 mid report (`MedMusketeer_FYP1_Mid_Report_LaTeX`, 2026-10-22) and the user's explicit clarifications. The mid report supersedes the proposal defence deck where they differ. If anything in a future conversation conflicts with this file, ask the user rather than assuming — and if the user confirms a change, update this file.

Last updated: 2026-10-23

## Project identity

- **Title:** Design and Development of a Secure Edge-Intelligent Cardiac Telemetry System for Remote Patient Monitoring
- **Short name:** MedMusketeer
- **Stage:** FYP-1, after the mid report (Stream A: research-derived)
- **Institution:** FAST National University of Computer and Emerging Sciences, Islamabad
- **Supervisor:** Mr. Shams Farooq — **Co-supervisor:** Dr. Muhammad Asim
- **Team & ownership:**
  - **Zain Ul Arifeen Sukhera** — Medical: ECG pipeline, edge models, medical evaluation
  - **Hasan Adil** — IDS/Cyber: traffic features, IDS models, IPS, attack evaluation
  - **Hamza Tariq** — Platform: IAM, security, hardware, cloud, dashboard (including the CA tool and provisioning chain)
- **Repositories:** master (integration point): https://github.com/hamzabu004/Med-Musketeer-Master-Repo; ECG classifier: https://github.com/zsukhera/arrhythmiaClassifier; IDS/IPS: https://github.com/HasanAdil23/ids-iot-combined. The ECG and IDS repositories are to be merged into the master repository.

## Core problem

Reliable ECG (electrocardiogram) screening on resource-constrained wearable/edge devices is hard because of limited compute, memory and energy. Network attacks can additionally disrupt secure communication and delay or compromise delivery of critical health alerts. The project must jointly solve a **model problem** (lightweight arrhythmia classification) and a **security problem** (protecting telemetry and detecting attacks) without treating them independently.

- **Deployment setting:** old-age homes, hospital wards, remote patients
- **Stakeholders and human roles:** see "Human roles" below.

## Research orientation / publication goal

Publication is an explicit goal. The research has **two strands**:

1. **Secure communication.** Experiment with and benchmark **recent, IoT-friendly, resource-light secure communication and authentication protocols** for the wearable↔gateway and gateway↔cloud links (e.g. MQTT+TLS vs lightweight/certificateless schemes and CoAP+DTLS).
2. **Arrhythmia classification on edge devices.** The effectiveness of TinyML/TinyDL for arrhythmia classification on microcontroller-class hardware, and the feasibility of **knowledge distillation** as an optimisation for edge devices (does a distilled student keep enough of a teacher's accuracy within the wearable's memory, latency and power limits).

**Boundaries of the secure-communication strand:**
- The benchmarking axis is **transport/auth protocols only** — it does NOT extend to comparing IDS/IPS approaches; IDS/IPS remains an implementation deliverable, not a benchmarking/publication axis.
- **Fixed protocol for FYP-1: MQTT+TLS.** The FYP-1 benchmark varies the **path** (fixed gateway vs mobile relay), with the wearable's screening result triggering each alert. Other protocol/auth candidates are compared against this baseline later as a separate axis; a full factorial across protocols is out of scope for FYP-1 — flag if a future request assumes the full cross was run.
- Within the baseline, the **certificate key type (RSA vs EC P-256)** is a separate benchmarked variable.
- There is **no continuous-vs-alert-only transmission axis**: ECG is never streamed continuously (ADR-1 in the report). Only screening-flagged alert segments and doctor-requested recordings leave the wearable.
- **The mobile-relay-vs-Tethys distinction is a design justification, not a standalone research contribution.** Frame it as "we adopted X because Y, distinct from Tethys's use case," not as a novel Tethys alternative.
- Because the transport/auth layer is itself the thing being benchmarked, cloud-side ingestion stays **protocol-agnostic/swappable**.

**Boundaries of the arrhythmia-classification strand:**
- Models are evaluated on **patient-level splits** and measured on the real ESP32-S3, not on laptop-class hardware. Random beat-level splits are not used for reported results (they leak patient information).
- Experiments progress teacher → normally trained student → distilled student → INT8-quantised student, so the effect of distillation and of quantisation can each be isolated.
- A teacher is locked only once it reaches **≥95% accuracy on both the binary and the five-class (AAMI N, S, V, F, Q) task** on the patient-level test set (macro-F1 and per-class recall reported with it). Distillation is adopted only if a distilled student beats the same student trained normally.

Implementation detail (checkpoint timestamps, clock sync, the gateway-vs-cloud classification confound) lives in `stack.md`.

## Locked scope

**Committed (must be delivered):**
- Lightweight multiclass arrhythmia classification, with on-device TinyDL screening
- Both communication paths (fixed gateway and mobile relay — see architecture below)
- IDS/IPS at the gateway, with replay-attack handling included
- IAM for human users (system admin, organisation admin, doctor, patient), for organisations as the clients to which devices are issued, and for devices (wearable and fixed gateway)
- Cloud platform (data/API/dashboard backend), including:
  - Device registry + live status for registered wearables/fixed gateways (the mobile relay is not a registered device)
  - Ingestion of IDS/IPS events/records from the gateway for the system admin (the detection logic itself stays gateway-side — the cloud only stores/surfaces the records)
- Secure device provisioning: CA tool, writing credentials to the wearable over serial, deploying credentials to the gateway over SSH, and QR-based BLE provisioning of gateway and Wi-Fi settings
- Wearable firmware in C (ESP-IDF) for the ESP32-S3, a Raspberry Pi gateway, Android provisioning and relay apps, a cloud backend, and a web dashboard
- Security and performance evaluation of the above on the prototype hardware

**Explicitly excluded (out of scope — do not implicitly add):**
- Physiological spoofing and adversarial ECG manipulation
- Firmware integrity, including secure boot and flash encryption (credentials sit in plain flash as an accepted shortcut)
- Gateway/platform host integrity beyond what network-based IDS/IPS can detect (rootkit persistence, tampered OS image, a locally-exploited vulnerability with no anomalous network signature, physical/insider access to the RPi). IDS/IPS as scoped operates on network traffic and structurally cannot see host-level compromise. The gateway's trustworthiness as a node is an assumed boundary, not something this project verifies.
- Network-exposed signing, an HSM, and an offline CA signing ceremony (the CA is a passphrase-protected key on one machine)
- Clinical validation, regulatory approval, or use on real patients — the system is a research prototype, not a diagnostic device
- A patient-specific digital twin (researched only; a possible extension if time permits)

**User clarifications that override the source proposals:**
- Replay attack handling **is included** in scope.
- The mobile relay is **relay-only** — it must never hold or use payload decryption keys. The Android phone is **not a MedMusketeer device/security principal**: it has no device-registry identity or MedMusketeer client certificate merely for relaying traffic; the wearable remains the authenticated principal end-to-end on the mobile path.
- "FYP-1 Final" targets a **complete, integrated implementation** of both routes, IDS/IPS, IAM and cloud (not just a partial core).
- **Human roles are tentative** and may still be added or renamed. IAM design keeps roles/policies as data (configurable), not hardcoded.

## Human roles

| Role | Level | Responsibilities |
|---|---|---|
| **System admin** | Whole system | Registers devices (CA custodian) and organisations, grants device access to organisations, monitors device security and IDS/IPS records. Sees **no** patient or doctor records. |
| **Organisation admin** | One organisation | IT admin of a client hospital/practice: manages its patient and doctor accounts, records disorders, issues its wearables to patients, assigns doctors, exports patient data. |
| **Doctor** | One organisation | Recommends patients for remote monitoring; views ECG, classifications and alerts of their own patients; acknowledges every alert; requests on-demand ECG. |
| **Patient** | One organisation | Wears the issued wearable; views their own data on the web or a phone. |

An **organisation** is a client of the system (a public or private practice or hospital). A device is granted to at most one organisation at a time; the organisation issues a wearable to one patient at a time.

## System architecture

```
Wearable (ECG acquisition, TinyDL screening, alerts with the triggering segment, on-demand ECG)
   │
   ├── Fixed path (trusted) ──► Fixed gateway: multiclass ECG classification + IDS/IPS
   │                                 │
   └── Mobile path (untrusted) ──► Mobile relay: transport bridge only; no device identity or decryption keys
                                        │
                                        ▼
                              Cloud backend: multiclass ECG (mobile path only),
                              IAM / data / API
                                        │
                                        ▼
                          Dashboard (patient, doctor, organisation admin, system admin views)
```

- **Wearable hardware:** ESP32-S3. ECG front end: AD8232 analog module in hand, **used for testing only**; a 2-lead **ADS1292** digital front end (which the product requires) has been requested from the hardware lab and not yet received.
- **Fixed gateway hardware:** Raspberry Pi 4B (trusted — may decrypt and classify), hosting its own WPA2 hotspot.
- **Mobile relay:** Android phone acting only as an untrusted communication bridge. It is not a MedMusketeer device/security principal, is not enrolled in the device registry, and receives no MedMusketeer client certificate or payload decryption keys. Wearable identity/authenticity remains end-to-end to the cloud.
- **Path selection:** a physical button on the wearable selects one path at a time; no automatic failover.
- **Fixed path:** authenticated links; trusted gateway does local multiclass classification.
- **Mobile path:** the cloud performs the multiclass classification since the relay cannot decrypt. Cloud inference is mandatory on this path.
- Authenticated on-demand commands return over the corresponding protected route.

## Evaluation plan

- **ECG:** accuracy, macro-F1, balanced accuracy, per-class recall
- **Edge:** latency, RAM, flash, energy
- **Security:** detection rate, false positives, response time
- **System:** alert latency, reliability, recovery

**Risks/dependencies:** limited/imbalanced ECG data, wearable resource constraints, the ADS1292 not yet received, hardware/dataset/network/library dependencies.

**GenAI boundary:** GenAI (LLMs) may assist with coding/debugging; final code, design decisions and results must be human-reviewed and validated by the team — never presented as unverified LLM output.

## Measured results so far (from the mid report, Chapter 8)

Only these have been measured. Everything else is a target.

- **ECG:** base-paper method (LightGBM) replicated on a patient-level split: **72–77% accuracy** for both binary and five-class (100 Optuna trials for five-class, 50 for binary, each repeated 5 times) — well short of the 95% teacher target. The base-paper method is therefore **dropped**; Iteration 2 moves to new feature sets, a wide classical-ML search, and 1D-CNN/RNN/LSTM/KAN-Former in parallel.
- **IDS (offline, CICIoMT2024):** binary — Random Forest 98.00% accuracy, XGBoost 98.50%; multiclass — Random Forest 84.14% accuracy / 82.56% macro-F1, XGBoost 81.37% / 79.78%. Offline only; no testbed or zero-shot results yet.
- **Provisioning chain and first fixed-path hop:** 56 automated tests pass (CA tool, secret scan, broker interop on a container broker); hardware procedures recorded. The wearable connects to the Pi's Mosquitto over mTLS and its periodic test alert is received. Evidence: `docs/testing/evidence/2026-10-22/`.

## Datasets

- **MIT-BIH Arrhythmia Database** — annotated beats; MLII lead first; AAMI mapping to N, S, V, F, Q; patient-level splits. Sampled at 360 Hz.
- **PTB-XL** — 12-lead, record-level rhythm-label study with multilabel structure; five diagnostic superclasses ≠ arrhythmia classes. Keep label spaces separate from MIT-BIH; do not conflate the two tasks.
- **CICIoMT2024** (Kaggle mirror, assumed content-equivalent to the official release) — IDS training; 45 numeric traffic features that the gateway must reproduce from its own traffic.

## Timeline / iterations

- **Iteration 1 (done):** secure-provisioning slice — CA tool, wearable credentials, BLE provisioning app, gateway broker, first fixed-path messages.
- **Iteration 2:** ECG evaluation on patient-level splits; the wearable's test alert replaced by the planned alert payload; ACL denials verified on the Pi itself.
- **Iteration 3:** cloud backend setup — PostgreSQL + TimescaleDB, device registry with organisations and device grants, ingestion API, EMQX with two listeners, ZITADEL with the four roles.
- **Iteration 4:** uplink bridge from the gateway broker to the cloud over mTLS (`attested_by`, backlog upload); verified wearable → cloud database.
- **Iteration 5:** edge model on the device, gateway classifier and uplink integration, IDS/IPS on the gateway with overhead measurements.
- **Iteration 6 (end of FYP-1):** relay app and envelope, dashboard, integrated baseline validation of both routes.

**Milestones:**
- **FYP-1 Mid (Week 8):** model baselines, ECG acquisition, gateway transport, dashboard prototype, requirements/design. Partly reached; secure provisioning delivered in addition.
- **FYP-1 Final (Week 16):** **complete implementation** — both routes, IDS/IPS, IAM, cloud; integrated baseline validation.
- **FYP-2 Mid (Week 8):** model/policy refinement, hardware profiling, attack stress tests (including mobile-path attacks), failure recovery, deployment trials.
- **FYP-2 Final (Week 16):** held-out evaluation, protocol-candidate comparison, final deployment, installation guide, report, handover.

(Week numbers are estimates to be aligned with the official FYP calendar; no dates are assigned to iterations yet — flag this if asked to treat them as fixed.)

## POC / current evidence

- Dashboard (proof of concept, deployment/interaction only): https://med-muskeeter.vercel.app/
- **Important:** the POC only demonstrates dashboard interaction and deployment — never imply it validates model, hardware or security performance.
- The new dashboard will be hosted at the same URL.

**Key related research consulted:**
- Knowledge-distillation lightweight arrhythmia classification (teacher/student)
- KAN-Former (multi-scale conv + attention + KAN, pruned/INT8, Cortex-M4)
- RNN arrhythmia classification on STM32 (MIT-BIH, AAMI protocol)
- TinyML arrhythmia classification on the ESP32-S3
- CMAP — certificateless MQTT authentication for medical IoT (ECC, Raspberry Pi 3)
- Ultra-lightweight anonymous auth for telehealth (Ascon AEAD)
- Tethys — untrusted smartphone-as-gateway sensor collection model (basis for the mobile relay-only design)
- MQTT broker end-to-end security models (double-encryption/broker re-encryption overheads)

**IDS/IPS and attack testing** are committed components. Their methodology and the attack-testing infrastructure live in `stack.md`. That is the IDS/IPS implementation methodology, not a benchmarking comparison — keep it distinct from the protocol/auth benchmarking axis.

## Rules for any session working on this project

1. **Never state or imply unmeasured results.** Only the figures under "Measured results so far" (and any new data the user supplies) are results. Everything else — including all benchmark, edge and system figures — is a target/planned/to be evaluated.
2. **Don't expand scope silently.** If a request implies work outside "Committed" (e.g., adversarial ECG defenses, firmware integrity, spoofing detection, a digital twin), flag that it's out of the locked scope before proceeding.
3. **Keep the mobile relay transport-only.** Any design/code touching the mobile path must not give it payload decryption capability or silently turn the Android phone into an enrolled MedMusketeer device/security principal. The wearable remains the authenticated identity on the mobile path.
4. **Keep MIT-BIH and PTB-XL label spaces separate** — don't treat PTB-XL diagnostic superclasses as arrhythmia classes interchangeable with MIT-BIH beat labels.
5. **Keep the protocol/auth benchmarking axis scoped to transport + authentication only.** Don't drift it into an IDS/IPS-approach comparison. Don't oversell the mobile-relay-vs-Tethys distinction as a standalone publishable contribution.
6. **Patient-level splits only** for any reported ECG result.
7. **This file is the scope reference, not the progress tracker.** Progress lives in the mid report and `docs/testing/`; open questions live in `gaps.md`.
