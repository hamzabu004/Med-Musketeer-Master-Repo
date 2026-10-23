---
name: medmusketeer-stack
description: Cloud/platform stack and architecture decisions for MedMusketeer. Companion to medmusketeer-fyp (scope.md) — that file defines *what* the project is; this file defines *how* the cloud/platform layer is built. Consult before writing cloud backend code, infra config, onboarding flows, transport/authentication/envelope code, or the attack-testing module.
---

# MedMusketeer — Cloud/Platform Stack & Architecture

This is a **technical decision record**, not the scope-lock file. If a decision here ever conflicts with `scope.md`, that file wins on scope; this file wins on implementation detail. Update this file as stack decisions evolve — it's expected to change more often than the scope-lock file. Companions in this folder: `mqtt-fixed-path-topics.md` (fixed-path topics and ACLs), `ca-tool-spec.md` (CA tool), `cloud-backend.md` (Iteration 3 cloud backend decisions D1–D10), `gaps.md` (what is still undecided). The FYP-1 mid report (Chapter 5) holds the same decisions as ADR-1 to ADR-8, plus the full cloud schema.

**Status markers used in this file:** **Decided** = confirmed by the team. **Proposed** = drafted here but not yet confirmed — do not treat as locked. **Open** = unresolved. **Implemented** = built and tested (evidence in `docs/testing/`). Last updated: 2026-10-23.

## Core design principle: protocol-agnostic ingestion

Because transport/auth protocol benchmarking is a research goal (see scope-lock file), the cloud must not hardwire one protocol or one device-credential lifecycle as if settled. A **transport/auth adapter layer** sits between the wire and everything else:

```
[Wearable / fixed gateway / mobile-relay transport] → transport/auth adapter (MQTT+TLS today | future: CoAP+DTLS | certificateless-X)
                            │  (per-adapter: handshake time, auth overhead, msg size logged)
                            │
                            ├── device identity/auth layer
                            │   canonical device_id stays stable; credential lifecycle is scheme-specific
                            ▼
                    Ingestion API (single internal contract)
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼              ▼
       Time-series DB   Relational DB   Notification bus
       (ECG)            (device/IDS     (dashboard)
                          registry/logs)
```

Each adapter speaks one protocol/authentication scheme, resolves the authenticated registered device to a stable canonical `device_id`, then hands a normalized message to the ingestion API. DB writes, classification triggers, IDS/IPS event storage, and notifications never depend on whether the device authenticated with X.509/mTLS, DTLS credentials, or a future certificateless scheme. Swapping/adding a protocol/auth candidate = new adapter/credential-lifecycle implementation, not a platform rearchitecture. The Android mobile relay is transport-only and is not resolved as a MedMusketeer device identity.

## Communication & authentication matrix

| Link | Protocol | Authentication / protection | Status |
|---|---|---|---|
| Wearable ↔ fixed gateway | MQTT over TLS to a **local broker on the Pi** | mTLS (X.509); wearable pins the gateway **role name** (not a specific gateway ID), gateway/local broker pins the wearable's CN; certificate key type (RSA vs ECC) is a benchmarked variable | **Decided**; **Implemented** for test alerts (local broker: Mosquitto) |
| Fixed gateway ↔ cloud | MQTT over TLS to EMQX (**private-CA listener**) | mTLS; gateway is a registered principal; EMQX auth hook checks credential status live; server cert from the private MedMusketeer CA, pinned by CN/SAN | **Decided** |
| Wearable ↔ mobile relay (phone) | BLE GATT (write + notify), app-level chunking | LE Secure Connections pairing = link hygiene only, never identity; payload protected by the application-layer envelope | **Decided** |
| Mobile relay ↔ cloud | MQTT over **server-authenticated** TLS to EMQX (**public-cert listener**) | Authenticates the server only, using a public-CA (Let's Encrypt) cert on the cloud's public domain; phone is not a principal and holds no device credential; wearable identity comes from the envelope | **Decided** |
| Wearable → cloud payload via relay | Application-layer envelope (Option B) | Static ECDH + HKDF + AEAD, monotonic-counter replay protection | **Decided** approach; construction details **Proposed** (see Envelope specification) |
| Human ↔ dashboard | HTTPS + WebSocket | ZITADEL OIDC/OAuth; public-CA (Let's Encrypt) cert on the public domain | **Decided** |
| Provisioning app → wearable (Wi-Fi + broker settings) | QR code on the wearable OLED, then BLE GATT write of one JSON settings document | LE Secure Connections with a passkey shown on the OLED; settings validated on the device. Certificates never travel over BLE (they go over serial, see "Device provisioning") | **Decided**; **Implemented** (ADR-3) |

**Identity consequence of the two paths (by design):**
- **Fixed path:** the wearable authenticates to the *gateway* (trusted, per the architecture). The cloud learns about the wearable through the gateway, so wearable identity on this path is **gateway-attested**, not end-to-end.
- **Mobile path:** the wearable stays the authenticated principal **end-to-end** to the cloud through the untrusted phone.

**Coverage gap to document, not hide:** the mobile path does **not** traverse the gateway, so the gateway IDS/IPS does not see it. In FYP-1 its only protections are cloud-side (EMQX ACLs/rate limits, envelope verification, counter window). Mobile-path attack testing is deferred to FYP-2.

### Wearable ↔ fixed gateway — MQTT over mTLS (Decided; local broker: Mosquitto, Decided)
- A **local MQTT broker on the Raspberry Pi** (**Decided: Mosquitto**) with a TLS listener that requires client certificates. The broker maps the client cert CN to the username (Mosquitto: `require_certificate` + `use_identity_as_username`) and applies per-device topic ACLs, so a wearable can only publish/subscribe under its own `device_id`.
- The wearable verifies the gateway's certificate by chain plus a **role-name SAN pin** (`gateway.medmusketeer.local`), not a gateway-specific `device_id`. No gateway ID is flashed into the wearable, so gateways can be replaced or added without reflashing wearables. See "Gateway identity: role pin" and the pinning rules in the envelope-security section.
- Gateway services subscribe to the local broker, run classification and IDS/IPS, then act as an MQTT client toward EMQX (next subsection).
- **Why a local broker:** keeps the gateway working with the cloud unreachable (required by the IPS scope), gives keepalive/LWT for free, and keeps the "MQTT+TLS" benchmark label true on both legs.
- **Costs to accept:** a second broker to harden and monitor (it is part of the attack surface the IDS must cover), and wearable identity toward the cloud becomes gateway-attested.
- Certificate key type is a benchmarked variable (see the candidate registry). CMAP, if built later, would replace only this leg.

#### Local broker choice: Mosquitto (Decided)
- **Why:** lightweight enough to share the Pi with the classifier and IDS; cert-CN-to-username mapping and per-device `%u` ACLs are built in; keeps the fixed path working with the cloud unreachable; provides keepalive and LWT.
- **Alternatives considered (not benchmarked):** NanoMQ — its file ACL documents no `%u`-style per-device topic patterns, so per-device rules or an HTTP auth service would be needed. EMQX on the Pi — heavier on a device also running the classifier and IDS, and the ACL design would need rebuilding in EMQX's rule system. Footprint on the Pi 4B was not measured.
- **Costs accepted:** Mosquitto exposes no per-client connect/disconnect events (only aggregate `$SYS` counters), so wearable presence relies on a retained `status` topic plus LWT; and it is a second broker technology to harden and monitor.
- **Verification status:** the cert CN becoming the username has been observed on the Pi. The `%u` ACL denials were verified on a container broker running the Pi's configuration (TC-B01 to TC-B04, `tools/ca-tool/tests/test_broker_interop.py`); repeating the denials on the Pi itself is planned for Iteration 2. An unauthorized publish is dropped silently on MQTT 3.1.1, so judge by what a monitor subscriber or the broker log shows. Setup script: `tools/Fixed-Gateway-Setup/setup_mosquitto.sh`. Separately, Mosquitto accepts any cert the private CA signed; restricting to registered wearables is covered by the local-allowlist Open item in "Gateway identity: role pin".
- **No native Mosquitto bridge to EMQX.** The uplink is a separate gateway service acting as an MQTT client toward EMQX, because the gateway must sit between the brokers: it adds `attested_by` to forwarded messages, forwards only what has passed classification/IDS, composes its own `mm/gateway/{gw_id}/...` messages (ids_event, status, backlog), controls outage buffering and backlog upload per the IPS methodology (wearables shown as unknown/stale while the cloud is unreachable), and offers a place for latency checkpoints and a clean credential boundary. Cost accepted: the bridge service must be written, tested and hardened, and adds a small processing delay on the fixed path.

### Fixed gateway ↔ cloud — MQTT over mTLS to EMQX (Decided)
- The gateway is a registered infrastructure device with its own `device_id` and credential; EMQX's auth hook queries `device_credentials.status` in Postgres on every connect (no caching needed).
- The gateway verifies the cloud's identity by CN/SAN pin, not chain trust alone. It connects to the **private-CA mTLS listener** (see "Certificate scope"), not the public-cert listener, and does not use the public domain cert as its trust anchor.
- The gateway publishes classification results, IDS/IPS events, wearable presence and backlog uploads; it subscribes to commands for its wearables. Buffering while the cloud is unreachable is governed by the IPS methodology.

### Wearable ↔ mobile relay — BLE GATT (Decided)
- One custom GATT service: a **write** characteristic (phone → wearable: commands, acknowledgements) and a **notify** characteristic (wearable → phone: envelope chunks).
- Negotiate a larger ATT MTU, then split each envelope into chunks with an application-level header (message id, sequence, last-chunk flag — exact layout **Open**). The phone reassembles the opaque blob and forwards it **without parsing or decrypting**.
- The wearable keeps a bounded buffer of unsent envelopes and resends until the phone acknowledges; duplicates are harmless because the cloud's counter window drops them.
- LE Secure Connections pairing only protects the local BLE link. Pairing must never grant the phone any MedMusketeer identity.
- Whether high-priority alerts get a separate indicate characteristic (per-message acknowledgement) is **Open**.

### Mobile relay ↔ cloud — MQTT over server-authenticated TLS (Decided)
- The phone app is an MQTT client of EMQX using ordinary server-authenticated TLS. It has no client certificate, no registry entry and no device credential.
- **Server cert (Decided): public-CA cert (Let's Encrypt) on the cloud's public domain.** The phone verifies it through the OS trust store, so the app bundles no `ca.crt` and needs no custom trust configuration. This listener is separate from the gateway's mTLS listener.
- **EMQX ACL (Proposed):** relay connections may publish only to `mm/mobile/+/{telemetry,alert,heartbeat}` and subscribe only to `mm/mobile/+/command`. The phone cannot be authenticated per device, so commands are protected by the envelope (signed/encrypted for the target wearable), not by topic access.
- **Topic `device_id` is an untrusted routing hint.** The cloud adapter must take the authoritative `device_id` from the authenticated envelope header and drop-and-log any message whose topic and envelope disagree.
- **Relay abuse control (Proposed): none relay-specific in FYP-1** — no relay token or shared app key; only basic EMQX ACLs/rate limits. If a token is added later for abuse control it stays separate from device identity and from payload keys.

### MQTT topic structure (base Decided; details Proposed)

`mm/{path}/{device_id}/{msg_type}` with `path ∈ {fixed, mobile}` and `msg_type ∈ {telemetry, alert, heartbeat, command, result}`, plus `status` and `command_ack` on the fixed path (Decided; in the implemented ACLs). The fixed-path detail, including ACL files, is in `mqtt-fixed-path-topics.md`.

| msg_type | Fixed path | Mobile path |
|---|---|---|
| `telemetry` | On-demand recordings only (Decided): continuous ECG streamed after a doctor's request command, for that recording. Wearable → local broker; gateway classifies and forwards to EMQX | Wearable envelope → phone → EMQX; cloud classifies |
| `alert` | Screening-triggered alert with the triggering ECG segment (the main data flow) | Same |
| `status` | Retained presence; LWT publishes `offline` | Not used — heartbeat envelope instead |
| `command_ack` | Wearable acknowledges a command | Carried in an envelope (detail Open) |
| `heartbeat` | Not used — MQTT keepalive/LWT carries presence (see liveness section) | Wearable-originated heartbeat envelope |
| `command` | Cloud → gateway → wearable (authenticated) | Cloud-signed envelope → phone → wearable via BLE write |
| `result` | Classification result produced by the gateway | Classification result produced by the cloud |

- `device_id` in these topics is the wearable's canonical UUID. Both brokers apply ACLs keyed on the authenticated identity (cert CN on the fixed path).
- **Proposed extension for gateway-level events:** `mm/gateway/{gateway_device_id}/{ids_event|status|backlog}` for IDS/IPS records, gateway status and backlog uploads.
- The LWT topic (`status`) and command-acknowledgement topic (`command_ack`) are settled for the fixed path. The implemented test alert uses QoS 1. Telemetry QoS and the remaining QoS/retain choices are **Open**; whatever QoS telemetry uses is held constant across both paths.

## Recommended stack

| Layer | Choice | Why |
|---|---|---|
| MQTT broker | **EMQX 6.3.2**, self-hosted single node, pinned (`emqx/emqx:6.3.2`; Business Source License 1.1, whose grant covers a single node and academic use — see `cloud-backend.md` D10) | Native TLS for the FYP-1 baseline; auth-hook/ACL plugin system means swapping in a certificateless scheme later doesn't require replacing the broker; exposes per-client connect/disconnect events useful for latency checkpointing |
| Local broker on fixed gateway | **Mosquitto** (Decided) on the Raspberry Pi | Terminates wearable mTLS locally so the fixed path keeps working with the cloud unreachable; lightweight; cert-CN-to-username and per-device ACLs built in |
| Transport/auth adapter layer | Thin Python service(s) between the wire/broker and the ingestion API | Keeps protocol and device-authentication swap-in/out cheap; emits the same normalized authenticated-device contract downstream |
| Ingestion API | **FastAPI** | Single internal contract regardless of which adapter delivered the message |
| Time-series DB (ECG) | **TimescaleDB** (Postgres extension) | Hypertables for waveform chunks; same engine as relational data — one DB to run |
| Relational DB (device registry, credential references, IDS/IPS event log, attack log, application relationships/policies) | Same **Postgres** instance, separate schema | Stores MedMusketeer domain/device data; human authentication stays in ZITADEL rather than being duplicated as a second IAM source of truth. Schema designed (see "Cloud database schema"); implemented in Iteration 3 |
| Human IAM | **ZITADEL** | API-first OIDC/OAuth IAM for the four roles (system admin, organisation admin, doctor, patient) and organisations; FastAPI integrates its management APIs so routine IAM administration stays inside the MedMusketeer platform UI |
| Notifications (web dash) | WebSockets via FastAPI, backed by Postgres LISTEN/NOTIFY or Redis pub/sub | Real-time alert push without a heavyweight message queue |
| Hosting | **A second Raspberry Pi as the cloud server first** (Decided), behind a public domain with automatically renewed certificates; a hosted VM (e.g. DigitalOcean Droplet or free-tier Oracle Cloud ARM) later if the budget allows. Dashboard POC on Vercel | Full control over broker/adapter config; no platform-imposed protocol assumptions. Cloud server not yet set up |
| Phone apps (provisioning, relay) | **Native Android, Kotlin + Jetpack Compose** (Decided) | Provisioning app implemented (`apps/provisioner/`); relay app not started |
| Gateway platform | Raspberry Pi OS Bookworm, NetworkManager WPA2 hotspot (`10.42.0.1`), Tailscale for remote admin, Python services | Controlled testbed network with known addressing; setup in `tools/Fixed-Gateway-Setup/` |

**Explicitly ruled out:**
- **AWS IoT Core** — provisioning model assumes X.509-per-device identity as the only path, which fights a future certificateless-auth comparison. Wrong fit given the protocol-benchmarking goal.
- **Managed MQTT (HiveMQ Cloud)** — works for the MQTT+TLS baseline itself, but won't allow custom auth hooks for latency checkpointing or future protocol swaps without leaving the managed tier.

## Benchmark design (current scope)

- **Fixed for FYP-1: MQTT+TLS.** This validates the path benchmark harness; other protocol/auth candidates get compared against this baseline as a separate axis later, not folded into the path comparison now. See the candidate registry below for what is planned and when.
- **Axis varied for FYP-1:** path (fixed gateway vs mobile relay), with the wearable's TinyDL screening result triggering each alert. There is **no continuous-vs-alert-only mode axis**: ECG is streamed continuously only on demand, for a doctor-requested recording (ADR-1), so the earlier path × mode 2×2 is dropped. The path is an operator-set variable (mode button).
- **Methodology requirement:** checkpoint timestamps at each hop — wearable send/detect → gateway receive/classify (fixed path) → cloud arrive/classify (mobile path) → dashboard render — with clock sync (NTP) across devices. Naive wall-clock deltas across hops are invalid without this. On the fixed path the hop list includes wearable → local broker → gateway service. Timestamps used for benchmarking are never trusted by any security decision.
- **Known confound to report, not normalize away:** multiclass classification runs on the gateway on the fixed path and in the cloud on the mobile path, so end-to-end alert latency includes a different classification step on each path. Report transport latency separately from classification time.
- **QoS** for telemetry and alerts is held constant across both paths.

## Protocol/auth candidate registry & key-type benchmarking

**Baseline key-type variable (Decided; stated in the mid report):** the MQTT+mTLS baseline credentials are provisioned in **two variants, RSA and ECC (P-256)**, and compared on the ESP32-S3 (handshake latency, RAM, flash, energy, reconnect time after an outage). Key *generation* is a one-time build-machine step, so it does not matter for the comparison; the per-handshake private-key operation does. This is a transport/auth variable inside the MQTT+TLS baseline, run as a **separate axis**, not folded into the path comparison.

**CMAP is ECC-only by construction** (scalar multiplications) — there is no RSA variant of CMAP.

**Confound to control and report:** certificate-chain verification cost depends on the CA's signature algorithm. The CA key type is held fixed at **EC P-256** and stated (Decided in the CA tool); whether an RSA-CA variant is also run is Open.

| Candidate | Where it applies | Status | Key constraints / notes |
|---|---|---|---|
| MQTT+mTLS, RSA cert | Wearable ↔ gateway; gateway ↔ cloud | **Baseline variant, FYP-1** | RSA key size Open (2048 assumed) |
| MQTT+mTLS, ECC P-256 cert | Same | **Baseline variant, FYP-1** | Provisioning script is parameterized by key type |
| TLS-PSK | Wearable ↔ gateway | **Proposed** intermediate comparator | Closest conceptual relative of CMAP; cheap to add in ESP-IDF |
| CMAP (Javadi et al., IEEE Access 2026) | **Fixed path wearable ↔ gateway only** | **Proposed: FYP-2, after the baseline is complete** | ECC only; needs its own ECC keypair as a separate credential (`certificateless_cmap`), not the TLS key; 128-bit IDs (the paper's 2-byte example is too short); gateway-side allowlist of device public keys synced from the cloud registry (same signed/versioned/rollback-guarded sync problem as revocation); CMAP only authenticates and derives a session key, so payload encryption using that key must be designed separately; does not protect MQTT metadata (topics) the way TLS does; reference code is a Python proof of concept (`ecdsa` library), no MCU port; not suitable for the mobile path (interactive multi-message handshake conflicts with Option B) |
| Ascon-based protocol (Zeng et al., IEEE TMC 2025), adapted | Possibly fixed path | **Parked** | Source is a human-user login protocol (password + smartcard + biometric) — would need heavy adaptation for devices; analytical evaluation only; timestamp freshness is a problem on the mobile path; Ascon has no hardware acceleration on the ESP32-S3 (AES-GCM does), so it may be slower there — measure, don't assume |
| CoAP + DTLS | Wearable ↔ gateway | **Parked** | Listed in the scope-lock file as an example alternative |

**Comparison hygiene:**
- Measure everything on the real ESP32-S3 and Raspberry Pi, not laptop-class hardware; the papers' numbers are theirs and must never be presented as this project's results.
- Verify a paper's claims before citing them (e.g. CMAP's abstract and Table 6 disagree on mean run time, and its forward-secrecy claim only holds if at most one long-term key leaks; the Ascon paper claims perfect forward secrecy but its protocol has no ephemeral key exchange).
- All benchmark outputs are targets/planned until the team supplies measured data.

## Path selection: manual mode switch (Decided; behaviour details Proposed/Open)

**Decision: the wearable has a physical button that manually switches it between fixed mode and mobile mode. There is no automatic path selection or failover.**

| Mode | Radio / link | Connects to | Security |
|---|---|---|---|
| Fixed | WiFi client | Local broker on a fixed gateway | mTLS; gateway verified by role-name pin (see "Gateway identity: role pin") |
| Mobile | BLE (advertising; the app connects) | Phone relay, which forwards to the cloud | Application-layer envelope (Option B) |

**Rules:**
- **One path at a time.** The wearable is in exactly one mode; it never runs both paths simultaneously, so the same data cannot arrive twice via different paths.
- **The unused radio is off.** BLE advertising happens only in mobile mode, so the wearable's GATT service is not exposed to nearby phones while in fixed mode.
- **Same canonical `device_id` in both modes.** Switching changes the path, not the identity.
- **The button does not replace gateway registration.** The fixed gateway remains a registered infrastructure device with its own credential, and the wearable still verifies it in fixed mode (by role-name pin, see "Gateway identity: role pin"). The button only selects which path the wearable uses.
- **The mobile side is not a gateway.** The phone stays a transport-only, unregistered relay; "mobile relay" is the correct term, not "variable gateway".
- **The path is an explicit, operator-set benchmark variable** rather than a firmware decision, which keeps the path axis clean.
- **Out of scope here:** any user feedback indicator for the current mode is a hardware design decision and is not specified in this file.

**Decided (ADR-5):** before switching, the wearable publishes `offline` with `reason: "mode_switch"` on the current path and disconnects cleanly. Without it the gateway sees a dropped connection and the cloud could wrongly show the wearable as offline when it has only moved to the other path. See the liveness section for how presence is inferred on each path.

**Open:**
- What happens to buffered, unsent data on a mode switch (flush, carry to the new path, or drop).
- Whether the selected mode persists across reboot or defaults to a fixed mode.
- Button handling (debounce, long-press to prevent accidental switches).
- How the wearable locates the gateway on the network in fixed mode. Currently the broker address is provisioned over BLE (the Pi hotspot is `10.42.0.1`); mDNS or a hostname would be an alternative.
- The cloud schema has `devices.current_mode` (fixed | mobile | unknown); how it is updated from the two paths is Open.

## Gateway identity: role pin (Decided for FYP-1)

**Decision: the wearable does not have a specific gateway's `device_id` flashed in. It trusts any gateway whose certificate chains to `ca.crt` and carries the shared role name `gateway.medmusketeer.local` in its SAN. The cloud, not the wearable, records which gateway a wearable is sending through.**

- **Gateway certs** carry two identities: the gateway's own `device_id` (CN and SAN, as for every device) and the role SAN `gateway.medmusketeer.local`. The role SAN is added at issuance by the provisioning tool.
- **Wearable-side pin:** the wearable checks chain plus the role SAN, the same pattern it uses for `cloud.medmusketeer.local`. The role name is DNS-style, so ESP-IDF's `common_name` check applies directly and avoids the UUID-matching open item for this leg.
- **Cloud-side association:** each forwarded wearable message carries `attested_by = <gateway device_id>`. The cloud records the gateway each wearable is currently sending through (e.g. `current_gateway_id` and `gateway_last_seen` on the wearable's registry record; schema Open). Mobile-path messages have `attested_by = null`, so the association is cleared or marked stale when a wearable switches to mobile mode.
- **Reassignment or gateway replacement** needs no wearable reflash: the new gateway is provisioned with the role SAN, and the cloud picks up the association from its first forwarded messages.

**Residual risk to document (not hide):** a wearable will accept *any* registered gateway, so a compromised gateway credential can receive data from wearables that connect to it, and the pin no longer separates one gateway from another. It still cannot impersonate the cloud, because the cloud and gateways have different pinned identities. Mitigations in FYP-1: gateway credentials are revoked through the live registry check at EMQX, and the cloud flags a wearable that appears behind an unexpected gateway.

**Documented hardening (not built in FYP-1):** cloud-signed assignment, where the cloud sends the wearable a signed "your gateway is X" command (existing command envelope, counter-protected), stored on the wearable in NVS and pinned thereafter. This restores gateway-specific pinning while keeping the cloud authoritative and avoiding reflashing for reassignment.

**Open:**
- Whether the cloud only *observes* the gateway association or also *enforces* a pre-assigned wearable↔gateway mapping (rejecting forwarded data from unassigned gateways).
- How the gateway learns which wearables to accept locally (a local allowlist of wearable `device_id`s synced from the registry, versus accepting any registered wearable cert), since the local broker must keep working with the cloud unreachable.
- How the wearable locates the gateway on the network in fixed mode.

## Device onboarding

| Device/component | Connectivity | Onboarding approach (FYP-1) | Future upgrade |
|---|---|---|---|
| Wearable, fixed path | WiFi (client mode, joins the Pi gateway's hotspot; active when the wearable's mode button selects fixed mode) | **Implemented:** TLS key/cert generated on the build machine and written over serial to the `creds` partition by the CA tool; Wi-Fi SSID/password and broker host/port written by the provisioning app over BLE after scanning the wearable's QR code (passkey pairing). Registry registration follows once the registry exists | — |
| Wearable, mobile path | BLE to phone relay (active when the wearable's mode button selects mobile mode) | Same canonical wearable identity as the fixed path; BLE pairing/provisioning only establishes the local relay link. The wearable, not the phone, remains the authenticated security principal for patient telemetry. | More automated wearable provisioning if needed |
| Fixed gateway (RPi 4B) | Hosts its own WPA2 hotspot for wearables; uplink over Ethernet/Wi-Fi; Tailscale for remote admin | **Implemented:** gateway key/cert deployed over SSH by the CA tool (pinned host key). Registered as an infrastructure device once the registry exists | — |
| Mobile relay app (Android phone) | BLE to wearable + phone cellular/WiFi to cloud | **No MedMusketeer device enrollment, CSR, client certificate, or device-registry identity.** The app is an untrusted communication bridge that forwards the wearable's opaque protected envelope. It may use ordinary server-authenticated TLS/app transport to reach the cloud, but this transport must not grant it wearable identity or payload-decryption capability. | Relay-session hardening/rate limiting if required |
| System admin, organisation admins, doctors, patients (human) | N/A | ZITADEL-backed onboarding/login through MedMusketeer; FastAPI uses ZITADEL management APIs for routine user/role/organisation administration | — |

**Mobile-relay rule:** the Android phone is **not a MedMusketeer device/security principal**. It must not be issued a device certificate, added as `mobile_gateway` in the device registry, or given payload decryption keys. The cloud authenticates the **wearable identity carried by the protected message/envelope**, while the phone only transports it.

**Hard rule:** compromise or replacement of the phone must not require rotating the wearable's long-term identity/payload keys merely because the relay changed. Relay transport credentials, if any are introduced later for abuse control, remain separate from MedMusketeer device identity and from payload decryption keys.

### Device provisioning / CSR-signing workflow

**CA custody:** one private MedMusketeer CA (`ca.key`/`ca.crt`), held by the platform/IAM owner as a passphrase-encrypted file on a single machine — never in the repo, never on any device. `ca.key` is only ever touched at signing time (below); it is not reachable at runtime by any wearable, gateway, or the cloud. Flagged explicitly as an FYP-1 shortcut: not HSM-backed, no offline signing ceremony — acceptable for project scope, would need hardening for real deployment.

**Provisioning sequence (one tool, one custodian, per new device).** Steps 2–5 are implemented in `mmca`; the registry steps (1, 6) and the envelope/cloud material (7) wait for the registry and envelope work:
1. Mint the canonical `device_id` in the registry first (`devices` row, `status: pending`) — the cert is issued *for* an identity that already exists, not the reverse. Until the registry exists, `mmca` mints a UUIDv4 locally.
2. Generate the device's own keypair(s) **on the build/provisioning machine, not on-chip**. The TLS credential's key type is a parameter of the script (**RSA or EC P-256**, because key type is a benchmarked variable). **Wearables additionally get a separate EC P-256 envelope keypair** (never reuse the TLS key for the envelope). On-device key generation is deferred until on-device private-key storage hardening is decided — generating "securely" into plain flash gains nothing.
3. Build the CSR from that keypair, with CN/SAN set to the `device_id` from step 1 — this is where CN/SAN pinning's identity actually gets bound, not added later. **Gateway certs additionally carry the role SAN `gateway.medmusketeer.local`** (see "Gateway identity: role pin").
4. Sign the CSR against `ca.key`/`ca.crt` (the only step that touches the CA key) → `device.crt`.
5. Flash `device.key` + `device.crt` + `ca.crt` onto the device over serial, into the read-only `creds` NVS partition (wearables later also get their envelope private key; see step 7 for the cloud envelope certificate). `device.key` is deleted from the build machine after a verified flash. Gateways receive theirs over SSH instead.
6. Insert one `device_credentials` row per credential: the TLS credential (`auth_method: x509_mtls`, `key_type` recorded) and, for wearables, the envelope credential (`auth_method: ecdh_envelope`, `credential_ref` = the wearable's envelope public key fingerprint). Then flip the `devices` row to active.
7. **Wearables only:** also flash the cloud's envelope certificate (signed by the same CA, CN pinned to `cloud.medmusketeer.local`, EC P-256 with key-agreement usage, long-dated).

No network-exposed signing service for FYP-1 — local/manual only, given low device volume.

#### Provisioning tool (Decided: local CLI `mmca`; Implemented)

**Decision: the sequence above is implemented as one local command-line tool run by the CA custodian, not as a network service.** It keeps the rule that `ca.key` is never reachable at runtime and is only touched at signing time. Full spec: `ca-tool-spec.md`; code: `tools/ca-tool/`.

- **Implemented commands (Python ≥3.11):** `init-ca`, `replace-ca`, `issue wearable|gateway` (key type `ec_p256` or `rsa_2048`), `flash` (serial write to the wearable's `creds` partition with chip check and read-back), `deploy` (gateway credentials over SSH with host-key pinning), `erase esp|gateway`, `audit`.
- **Audit log:** append-only JSON lines recording what was issued, flashed, deployed or erased, when, and for which `device_id`; never secrets.
- **CA key handling:** `ca.key` stays passphrase-encrypted on the custodian's machine; the tool prompts for the passphrase and never stores it. Not HSM-backed, same FYP-1 shortcut as above.
- **Not built yet:** the registry link and `revoke` (marks the credential revoked in `device_credentials`, which EMQX's auth hook checks live on every connect), envelope keys, and the cloud certificate profiles. A thin PyQt6 front end over the same core is planned as Stage 2. No API and no remote signing.

**Open:** how DB access is configured for the registry steps, and whether a signed gateway-assignment command (see "Gateway identity: role pin") is later generated by this tool.

## Attack-testing / ground-truth infrastructure

- **Cloud: system-admin-only "Attack Test" module**, separate from the production patient/doctor data path.
  - `POST /attack-test/start` — `{attack_type, target_device_id, params}` → `attack_id`, logs `start_ts`
  - `POST /attack-test/stop` — `{attack_id}` → logs `end_ts`
  - Attack log table `attack_tests`: `test_id, target_device_id, triggered_by, attack_type, parameters, started_at, ended_at`
  - **Device registry flags testbed vs production devices** (`devices.is_testbed`) — attack triggers are refused against a production device.
  - Correlates each attack window against the IDS/IPS event log to compute detection latency, false negatives (no alert inside window), false positives (alerts outside any window) — this is the ground-truth source for the evaluation plan's IDS metrics.
- **Phone module (mobile-relay attack testing) — DEFERRED TO FYP-2; not built or run in FYP-1.** When built, it lives in a **dev/test build of the mobile relay app, stripped from production builds.**
  - Feasible without root (application-layer): MQTT flood, replay (duplicate a captured relayed payload — natural fit since the relay already handles encrypted payloads without decrypting them), malformed/fuzzed MQTT packets, TCP connection-flood/port scan.
  - Not feasible from an unrooted phone (network-layer, needs raw sockets/packet injection): ARP spoofing/MITM, SYN flood — run these from a separate testbed machine (laptop/RPi on the same test LAN), reporting into the same cloud Attack Test service.

## IDS/IPS methodology (Hasan's component — offline baselines measured; testbed results are targets)

**Data and modes:** the IDS models use the **45 numeric traffic features of CICIoMT2024**, so the gateway must compute the same features from its own traffic. The gateway runs in **IDS mode** (detect and log, no blocking) or **IPS mode** (apply a configured mitigation — reject or throttle the source — to traffic classified as malicious). Each detection produces a security event (time, predicted class, outcome, and in IPS mode the action and its result) uploaded to the cloud (`security_events`). Offline baselines (Random Forest, XGBoost; binary and multiclass) are in the mid report, Chapter 8.

**IDS methodology:**
1. Train/develop model on public IoMT attack data (CICIoMT2024)
2. Freeze the model
3. Zero-shot test on the team's own physical hardware testbed (no retraining at this step)
4. Measure the performance drop between public-data training and the physical testbed (planned measurement)
5. Apply a small amount of local adaptation
6. Measure recovery after adaptation (planned measurement)
- **Target/goal:** adaptation to zero-day attacks on the physical testbed.

**IPS methodology — when the gateway is detected under attack, it should:**
Reject/throttle the malicious source → preserve ECG acquisition → preserve TinyDL screening → preserve the high-priority alarm channel → buffer unsent measurements → reconnect/recover → upload the backlog once clear.
- **Target/goal:** resilience when under attack — graceful degradation with recovery, not detection alone.

**Practical zero-shot testing procedure:**
1. **Match the feature space** between the public IoMT dataset and your own testbed's traffic-capture pipeline first — feature mismatch (not real domain shift) is usually the biggest cause of a misleading "performance drop."
2. Stand up the physical testbed generating genuine benign traffic.
3. Reproduce the public dataset's attack categories against the testbed — you can only zero-shot test attack types the model actually saw in training.
4. Run the frozen model in inference-only mode (no weight updates) on captured testbed traffic.
5. Compare detection rate/false-positive rate here vs. the model's known numbers on the public dataset's own test split — the gap is the performance drop.
6. Only then apply local adaptation and re-measure for recovery.

## Cloud database schema (Designed; implemented in Iteration 3)

Full table with columns and types: mid report §5 "Data Design" (Table "Cloud schema" and the ERD). One PostgreSQL instance: ECG chunks and security events in TimescaleDB hypertables, domain data in ordinary tables. People are referenced by their ZITADEL subject; names and login data are not copied. Every user except the system admin belongs to one organisation, and organisation-level queries are filtered by it.

| Group | Tables |
|---|---|
| People and organisations | `organisations`, `users` (`zitadel_sub`, `role`, `org_id`, `status`), `patients` (pseudonym only), `care_assignments`, `patient_disorders`, `patient_exports`, `audit_log` (added in Iteration 3, `cloud-backend.md` D11) |
| Devices | `devices`, `device_grants`, `device_assignments`, `device_credentials`, `device_updates` (only if remote updates are adopted) |
| ECG and alerts | `monitoring_sessions`, `ecg_segments` (kind alert or recording), `ecg_chunks` (hypertable on `ts`), `classifications`, `alerts` (pushed via NOTIFY), `commands` |
| Security | `replay_windows`, `security_events` (hypertable on `ts`), `attack_tests` |

**Rules that shape the schema:**
- A monitoring session takes its `patient_id` and `org_id` from the device assignment active at `started_at`; they never change. Unassigning or reassigning a wearable ends its open session, so a previous patient's ECG is never attributed to the new one.
- Each alert segment or on-demand recording is one `ecg_segments` row grouping its chunks; a recording references the command that requested it.
- At most one open grant per device; one active wearable per patient; one active doctor per patient.
- **Retention:** the TimescaleDB retention policy drops only raw `ecg_chunks` after a limited period (period Open). Segments, classifications and alerts are kept. No foreign key points into `ecg_chunks`, so the drop is never blocked and never cascades.

## Human IAM vs device identity/authentication

**Human IAM is separate from device authentication.** ZITADEL handles **people** — system admin, organisation admins, doctors, patients — including login, OIDC/OAuth tokens, MFA and organisations. Routine IAM operations are exposed through the MedMusketeer admin UI via FastAPI calling ZITADEL's management APIs; admins should not need to open the ZITADEL console during normal operation. MedMusketeer/Postgres references each person by their ZITADEL subject (`users.zitadel_sub`, with `role` and `org_id` as data) and stores the application-domain relationships: organisation membership, device grants to organisations (`device_grants`), patient↔wearable issue history (`device_assignments`), and doctor↔patient care assignments (`care_assignments`).

**Access rules (Decided, report §5 Data security):** the API checks the role, the user's organisation, and the doctor assignment for every patient record, and filters ECG data on the `patient_id` and `org_id` carried by its session and segment. Only the system admin sees the registry, device grants, security events and attack tests, and the system admin sees **no** patient or doctor records. Grants, issues, assignments, exports and account changes are logged with the acting user (`audit_log`, `cloud-backend.md` D11). The API's ZITADEL access for account administration is a service account with the instance role `IAM_ORG_MANAGER` (D12).

**Device identity is protocol/authentication-neutral.** The registered MedMusketeer device security principals are the **wearable** and the **fixed gateway**. Each has a stable canonical `device_id` that is independent of whichever credential/authentication scheme is currently under test. The Android mobile relay is deliberately excluded from the device-identity model.

The transport/auth adapter must normalize successful device authentication into a common internal result, conceptually:

```text
{
  device_id: <canonical MedMusketeer device UUID>,
  device_type: wearable | fixed_gateway,
  auth_method: x509_mtls | ecdh_envelope | dtls_<scheme> | certificateless_<scheme>,
  attested_by: <gateway device_id> | null,   # set only for fixed-path wearable messages forwarded by the trusted gateway; null when authenticated end-to-end (mobile path)
  authenticated: true,
  auth_metadata: {...}    # benchmark/debug metadata only; downstream logic must not depend on its scheme-specific shape
}
```

**Permanent device registry fields (`devices`):** `device_id` (UUID = cert CN, canonical), `type` (`wearable` or `fixed_gateway`), `status` (pending | active | suspended | revoked), `is_testbed`, `current_mode` (fixed | mobile | unknown), `current_gateway_id` (nullable), and `last_seen`. Ownership is not a column: it comes from `device_grants` (organisation) and `device_assignments` (patient). Do **not** make certificate serial/expiry columns of the core device identity record.

**Scheme-specific credential records (`device_credentials`):** `credential_id`, `device_id`, `auth_method` (x509_mtls | ecdh_envelope | …), `key_type`, `credential_ref` (serial or fingerprint), `status`, `created_at`, `expires_at` (nullable), and scheme-specific `metadata` (jsonb). This lets one physical device retain the same `device_id` while its authentication method changes during experiments.

**Credential lifecycle is replaceable, not permanent platform logic.** Expose generic lifecycle operations such as `enroll`, `authenticate`, `rotate_or_update_credential`, and `revoke_or_disable`. Their implementation depends on the selected candidate:
- **MQTT+TLS/X.509 baseline:** device keypair/CSR or pre-provisioned key material → CA certificate issuance → mTLS authentication → certificate renewal/rotation → certificate revocation/check.
- **Future DTLS/lightweight/certificateless candidate:** use that scheme's own registration, authentication, key-update, and revocation/disable procedure. It must not be forced into certificate terminology if the scheme has no certificates.

For FYP-1, manual/pre-provisioned credential enrollment is acceptable for the baseline; automation of certificate renewal is not a permanent architectural requirement because later candidates may use a different lifecycle entirely.

**Registered device handling:**
- **Wearable:** generate/register the candidate-specific identity credential at build/onboarding time. The same canonical wearable `device_id` is used on both the fixed and mobile paths.
- **Fixed gateway:** register as an infrastructure device and provision whichever candidate-specific credential the current experiment requires.
- **Mobile relay:** **no MedMusketeer device credential is issued.** It does not receive a device certificate or registry identity merely for forwarding patient telemetry.

**Critical separation:** ZITADEL human IAM must never become the device-authentication mechanism, and the mobile relay must remain cryptographically unable to impersonate the wearable or decrypt its payload. The cloud must validate the wearable's identity/authenticity from the protected end-to-end message/envelope after it traverses the phone. Any ordinary phone↔cloud app/session protection used for transport hardening or abuse control is separate from MedMusketeer device identity.

## Certificate scope: private CA vs public cert (Decided)

**Decision: the public-CA cert (Let's Encrypt) on the cloud's public domain covers the dashboard and the mobile relay's MQTT listener. Everything tied to device identity stays on the private MedMusketeer CA.**

| Surface | Cert / trust anchor | Why |
|---|---|---|
| Dashboard (HTTPS + WebSocket) | Public CA (Let's Encrypt) | Browsers require a publicly trusted cert |
| Mobile relay ↔ EMQX (server-auth TLS) | Public CA (Let's Encrypt) | Phone verifies via the OS trust store; no bundled `ca.crt` or app-side trust management; phone holds no credential anyway |
| Gateway ↔ EMQX (mTLS) | **Private MedMusketeer CA**, CN/SAN pinned | Closed trust anchor; pinning is meaningful only against a CA you control; benchmarked RSA-vs-ECC cert variable stays under team control |
| Wearable ↔ gateway (mTLS) | **Private MedMusketeer CA**, CN/SAN pinned | Same |
| Wearable envelope key (cloud EC P-256, CN `cloud.medmusketeer.local`) | **Private MedMusketeer CA** | Not a TLS cert; end-to-end through the untrusted phone, independent of the public domain cert |

**Consequences:**
- EMQX runs **two listeners**: an mTLS listener (private-CA server cert) for gateways, and a server-auth listener (public cert) for mobile relays. Topic ACLs stay keyed to the authenticated identity on the gateway listener and to the relay ACL on the public listener.
- The public cert is **not** a trust anchor for gateways or wearables. Gateways and wearables never accept it in place of the private CA, and `crt_bundle_attach` remains ruled out on the ESP32-S3.
- The mobile path's security still comes from the envelope, not from the TLS cert. The public cert only provides ordinary transport protection and server authentication for the phone.
- This revises the earlier "no dependency on a real public domain" rationale: the cloud now has a public domain for the dashboard and relay. Device and envelope trust still does not depend on it.
- **Renewal:** Let's Encrypt certs are short-lived, so the dashboard and relay-listener certs need automated renewal (e.g. ACME client with EMQX/reverse-proxy reload). This is separate from the long-dated private-CA cloud cert in "Cloud cert rotation", which remains deferred.

## Mobile-path envelope security (wearable ↔ cloud, via untrusted relay)

**Decision: Option B — application-layer envelope crypto, not a live end-to-end TLS/DTLS session through the phone.**

The wearable encrypts/signs the payload itself, addressed to the cloud, *before* handing it to the phone. The phone ships that opaque blob to the cloud over its own ordinary session-level TLS (authenticates the phone app only, not the wearable). Chosen over a live TLS/DTLS session relayed transparently through BLE because that approach is fragile against BLE link drops and heavier on the ESP32-S3 — application-layer envelope crypto survives an intermittent relay link and matches the "opaque envelope" framing already used elsewhere in this file.

**CA structure: single private MedMusketeer CA, reused for both gateway and cloud trust anchors.** The wearable flashes one `ca.crt` used to verify both the fixed gateway's TLS cert and the cloud endpoint's cert/public key for envelope encryption. Rationale: no dependency on a real public domain for the testbed; one trust anchor to reason about and document. (A public CA/Let's Encrypt is used for the dashboard's browser-facing HTTPS and for the mobile relay's EMQX listener — separate certs, separate audience, not part of device/envelope trust. See "Certificate scope".)

**CN/SAN identity pinning is a non-negotiable requirement, not optional hardening — implement alongside the shared CA, not after.** Chain-of-trust validation alone (any cert signed by `ca.crt` is accepted) is insufficient once multiple gateways share a root with the cloud: it lets a compromised gateway's cert be used to impersonate the cloud to a wearable, and the exposure scales with gateway count. Every TLS/envelope verification the wearable performs must check the peer cert's CN/SAN against the expected identity for that connection — the fixed cloud identity `cloud.medmusketeer.local` for the cloud, and the **role name** `gateway.medmusketeer.local` for gateways — not just chain validity. This applies on both paths: wearable→gateway (fixed) and wearable→cloud (mobile). **FYP-1 pins the gateway by role, not by individual `device_id`** (see "Gateway identity: role pin"); this closes cloud impersonation by a gateway cert but not gateway-to-gateway impersonation, which is a documented residual risk with cloud-signed assignment as the future hardening.

**Implementation note — do not use `crt_bundle_attach`.** ESP-IDF's certificate-bundle API verifies against a bundle of many public root CAs (correct for talking to arbitrary standard TLS servers, e.g. OTA hosts) and is the wrong tool here — MedMusketeer's model is the opposite: one private CA, plus explicit per-connection identity pinning. Use `cacert_buf` (the single `ca.crt`) together with `common_name` + `skip_common_name = false` set to the *specific* expected peer identity per connection. **Open item to verify during implementation:** `common_name` is documented primarily as an SNI/hostname mechanism; confirm it does a literal CN string match against device-UUID-style CNs (not DNS-style hostnames) before relying on it — fall back to a custom `mbedtls_ssl_conf_verify` callback if it doesn't.

**Documented future hardening (not required for FYP-1 baseline, flag if skipped without reason):** split the shared root into a Device Intermediate CA (signs wearable/gateway certs) and a Server Intermediate CA (signs the cloud endpoint cert), both rolling up to one offline root. Contains blast radius if the device-issuance signing key is compromised. CN/SAN pinning alone is sufficient to close the known impersonation flaw for FYP-1; this is defense-in-depth on top of it, not a substitute.

### Envelope specification

**Decided:** Option B (application-layer envelope); monotonic-counter replay protection with a cloud-side window; GATT write/notify carriage; **forward secrecy is not a goal of this envelope** (documented as a limitation below, not offered as an option).

**Proposed construction (confirm before implementing):**
1. **Keys.** The wearable has a dedicated **EC P-256 envelope keypair**, registered as its own `device_credentials` row (`ecdh_envelope`). The cloud has an EC P-256 envelope key with a certificate signed by the MedMusketeer CA (CN `cloud.medmusketeer.local`, key-agreement usage), flashed onto the wearable at provisioning together with `ca.crt`. Because ECDH needs an elliptic-curve key, the envelope is ECC regardless of the RSA/ECC choice for the TLS baseline.
2. **Key derivation.** Static–static ECDH between the wearable key and the cloud key, then HKDF-SHA256 with `info = "mm-envelope-v1" || device_id || direction`, giving separate keys for wearable→cloud and cloud→wearable.
3. **AEAD.** AES-GCM (hardware AES on the ESP32-S3). Ascon stays a later candidate only.
4. **Header (sent in the clear, authenticated as AAD):** `version`, `msg_type`, `device_id` (16-byte UUID), `key_epoch`, `counter`. Body: ciphertext + 16-byte tag.
5. **Nonce** is built from the counter. The wearable persists its counter with a **persist-ahead reservation** (reserve a block, skip to the reserved value after a reboot) so a crash can never reuse a nonce under the same key.
6. **Cloud processing order:** parse header → look up `device_id` (active, correct testbed/production flag) → derive key → AEAD verification (reject silently on failure) → counter-window check → hand to the ingestion API. Apply rate limiting before the expensive steps.
7. **Replay protection:** per-device, per-direction sliding window over `(key_epoch, counter)`, stored in `replay_windows` (`highest_counter`, 64-bit bitmap); duplicates and below-window counters are dropped. Window size Open (64 as a starting point). A reset counter requires re-provisioning or a `key_epoch` bump.
8. **Return path (commands):** cloud → wearable envelopes use the cloud→wearable direction key and their own counter; the wearable persists the highest accepted command counter.
9. **Time is not trusted.** The wearable's time comes via the untrusted phone, so timestamps in payloads are informational/benchmark-only, never part of a security decision.

**Known limitations (state these in the report):**
- No forward secrecy: a leaked long-term key lets an attacker who recorded envelopes decrypt them.
- No non-repudiation: the AEAD key is symmetric and derivable by both sides, so the cloud could forge a "wearable" message.
- The relay sees metadata (`device_id`, `msg_type`, size, timing) and can drop, delay, reorder or duplicate envelopes. Duplicates are neutralized by the counter window; drops/delays are only *detectable* (heartbeat gaps), not preventable.

## Cloud cert rotation — mobile-path key distribution (FUTURE SCOPE, not FYP-1)

**Decision: out of scope for FYP-1.** Rotating the cloud's leaf keypair the wearable encrypts envelopes to on the mobile path is deferred, not built. FYP-1 uses a long-dated cloud cert that comfortably outlasts the project timeline (same move already made elsewhere in this file for on-device key generation and the offline-signing ceremony) — rotation during the project is treated as a non-event by design, not solved in software.

## Gateway/wearable credential revocation (fixed path) — PENDING, not yet confirmed

**Status: candidate design only — user has not confirmed this yet. Do not treat as a locked decision the way the cloud-rotation section above is.**

**The gap this would address:** on the fixed path, wearable↔gateway is a genuine live mTLS session (ESP makes a direct connection to the gateway), so a rotated cert is a non-issue — chain/CN-SAN gets re-checked fresh on every handshake automatically. What live TLS does *not* give you for free is **revocation before natural expiry** — if a device's credential is revoked (compromised gateway, stolen device) before its cert expires, a plain chain+CN/SAN check still passes. Same gap applies to gateway↔cloud, but that leg is trivial to close (the broker's auth-hook just queries `device_credentials.status` in Postgres live, on every connect — no caching needed since it already sits in front of the registry).

**Why wearable↔gateway is the harder case:** per the IPS scope, the gateway must keep doing local ECG acquisition/classification/alerting even when it can't reach the cloud — so a live "phone home to check revocation" call on every wearable handshake would work against that graceful-degradation requirement.

**Candidate mechanism (not yet approved):**
- Gateway periodically pulls a small CA-signed revocation list from the cloud whenever it *can* reach it (CRL-style: revoked `device_id`s + a version/timestamp), verifies the signature against `ca.crt`, and caches it locally.
- Rollback guard: reject any pulled list whose version is older than what's already cached, so a replayed stale "nothing revoked" list can't un-revoke a device.
- On each wearable↔gateway handshake, check the peer's `device_id` against this local cache in addition to the normal chain/CN-SAN check — no network round-trip required, so it degrades gracefully if the cloud link is down. Worst case is working off a slightly stale list, which would need to be an explicitly flagged tradeoff, not a silent gap.

**Open, unresolved even at the design level:**
- Whether this is worth building for FYP-1 at all, given the low device count and short project timeline — may be a case for the same "document as future hardening, don't build now" call made elsewhere in this file, rather than actual implementation.
- If built: revocation-list wire format, pull cadence, and how the gateway surfaces "operating on a stale revocation list" to the cloud/admin dashboard once reconnected.
- Whether the broker-side check (gateway↔cloud) and this local cache (wearable↔gateway) should read from one shared source of revoked IDs or can stay independent.

## Device presence/liveness detection (online/offline status)

**Decision: no application-level "ping the cloud" polling loop on either path — mechanism differs per path because the wearable's relationship to the cloud connection differs per path.**

**Fixed path (wearable → local broker on the gateway; gateway → EMQX):** use native MQTT liveness machinery on each hop, not custom heartbeat traffic.
- **Wearable ↔ local broker:** MQTT keepalive (PINGREQ/PINGRESP; broker treats the client as dead after 1.5× the agreed interval) plus Last Will and Testament registered at connect time. A clean disconnect should publish an explicit offline message instead of relying on the will. All of this rides the already-authenticated mTLS session, so presence adds no new auth surface.
- **Gateway reports wearable presence upward:** the gateway derives wearable online/offline from the local broker's retained `status` topic and LWT (Mosquitto has no per-client connect/disconnect events) and publishes it to the cloud. Fixed-path wearable `status`/`last_seen` is therefore **gateway-attested**.
- **Gateway ↔ EMQX:** the gateway has its own keepalive and LWT toward EMQX. EMQX per-client connect/disconnect events (also the benchmark checkpoint source) feed the gateway's `status`/`last_seen` directly.
- **Gateway unreachable ≠ wearable offline:** when the gateway drops off, the cloud should show its wearables as **unknown/stale**, not offline, until the gateway reconnects and uploads its backlog of presence events.

**Mode switching:** because the wearable is manually switched between paths (see "Path selection"), a wearable going quiet on one path may simply have moved to the other. A fixed-path disconnect followed by mobile-path envelopes (or the reverse) should be read as a mode change, not a failure, where an explicit mode-change message is available. How `status`/`last_seen` reconcile across the two paths is Open.

**Mobile path (wearable → phone relay → cloud):** broker/session-level liveness is insufficient here and must not be treated as a proxy for wearable presence. The wearable is never itself an MQTT client to the cloud broker on this path (per the Option B envelope design above) — only the phone holds that session. Phone-session-alive does **not** imply wearable-present (BLE out of range, wearable powered off, etc., are all invisible to the phone's own transport-level liveness).
- **Mechanism:** a wearable-originated heartbeat envelope — same auth/encryption scheme as the telemetry envelope (Option B, CN/SAN-pinned), minimal payload — relayed by the phone like any other envelope.
- **Cloud inference:** wearable considered offline based on **envelope-arrival gap** (no heartbeat or telemetry envelope within the expected interval), tracked independently from the phone's own transport-session state.
- **Why keep these separate signals distinct:** "phone alive, wearable silent" and "both offline" are diagnostically different states and should surface differently in the device registry / admin dashboard, consistent with the existing asymmetric trust model (wearable = real security principal, phone = transport-only, no separate identity).

**Device registry implication:** the schema has `devices.last_seen` and `current_mode`, but their semantics differ by path — fixed-path status derives from broker connection events (gateway-attested); mobile-path status derives from envelope-arrival timing, with the phone's session state as a secondary signal, not the primary one. How the two are reconciled is still Open.

## Open next steps (not yet decided)

The mid report's list of unsettled design items (§5 "Design items still to be settled") is mirrored here; `gaps.md` tracks the wider list.

- Telemetry QoS and payload format (the alert payload adds sequence number, sampling rate, lead, sample count, encoding — little-endian signed integers, Base64 inside JSON — and samples; no compression in the first phase)
- ECG sampling rate and window length (MIT-BIH is 360 Hz; the device must match training or the data must be resampled)
- Gateway discovery by the wearable (the broker address is currently provisioned)
- NTP on the gateway hotspot (required by the benchmark methodology)
- Enforcing (not just observing) wearable↔gateway assignment — observe-only is decided for Iteration 3 (`cloud-backend.md` D5); local wearable allowlist on the gateway
- Schema details still open within the design above (the normalised message, `attested_by` source, alert payload and gateway authentication are decided in `cloud-backend.md`)
- Envelope wire-format details: field widths, counter-window size, persist-ahead reservation block size, `key_epoch` handling on re-provisioning; confirm AES-GCM and the exact header/derivation
- BLE details: chunk header layout, MTU target, wearable buffer size, whether alerts get a separate indicate characteristic
- Mode-switch behaviour (buffered data, persistence across reboot, button handling)
- Mobile heartbeat interval/timeout, and how `status`/`last_seen` reconcile the two paths
- RSA key size (2048 assumed) and whether an RSA-CA variant is run
- ACL denials verified on the Pi itself (Iteration 2)
- The literal-name check in the ESP32-S3 TLS library for UUID-style names (`common_name`), and the gateway's outbound check of the cloud's identity
- Public-certificate operations: ACME client, automated renewal and EMQX reload, one shared public domain/cert or separate subdomains
- Phone-to-patient binding for the relay (see `gaps.md`)
- Whether fixed-path revocation (see "Gateway/wearable credential revocation") is built in FYP-1
- No relay-specific abuse token in FYP-1 (Proposed); the gateway-event topic extension (Proposed)
- Mobile-path abuse protection beyond basic EMQX limits, and all mobile-relay attack testing — deferred to FYP-2
- CMAP and TLS-PSK candidate work — planned after the certificate-based baseline is complete (see the candidate registry)
- Cloud cert rotation is deferred to future scope — nothing to build for FYP-1
