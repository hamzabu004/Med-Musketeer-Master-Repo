# MedMusketeer — CA & Provisioning Tool — Build Spec (Stage 1: CLI, Stage 2: GUI)

Companion to `stack.md` ("Device provisioning / CSR-signing workflow" and "Provisioning tool"). Status markers follow that file: **Decided** / **Proposed** / **Open** / **Deferred** / **Implemented**.

**Update (2026-10-24):** `mmca issue cloud` (the EMQX gateway listener's server certificate, section 4) is Implemented, and every certificate now carries key identifiers (Subject Key Identifier on the CA and leaves, Authority Key Identifier on leaves). Strict X.509 verifiers, such as Python 3.13+'s default TLS context, refuse leaves without an AKI and CAs without an SKI. A CA created before this change has no SKI, so chains from it still fail strict verification until the CA is replaced (`gaps.md`).

**Status (2026-10-23): Stage 1 (CLI) is Implemented** in `tools/ca-tool/` (`mmca`) and tested: 56 automated tests pass, plus hardware procedures on the ESP32-S3 and the Pi (`docs/testing/`). The implemented CLI differs from the original plan below in two ways: there is an `erase` command (section 5), and the registry link stays Deferred (`revoke` was later removed, see the update above). Stage 2 (GUI) is not started. Sections marked Proposed below describe the plan as built unless noted.

**Update (2026-10-29):** the `revoke` command is removed from the plan. Revocation is done through the cloud registry API and the dashboard (`/admin/devices/{id}/revoke`, `/admin/credentials/{id}/revoke`), which also update the gateways' revocation list (`cloud-backend.md` D16). The CA tool issues, flashes, deploys and erases; it does not revoke.

Last updated: 2026-10-29

## 0. Approach (Decided)

The tool is built in two stages over one shared core:

- **Stage 1: CLI.** Complete, scriptable, headless-testable provisioning tool. This is the deliverable that must work first.
- **Stage 2: PyQt6 GUI.** A **thin front end** over the same core and CLI functions. It collects inputs, shows progress and results; it contains no signing, flashing or deploy logic.

Consequences:

- **Signing stays local.** `ca.key` is only touched on the custodian's machine at signing time. No network service, no remote signing.
- The SSH feature **deploys already-signed material to the gateway**. It never signs remotely and never moves `ca.key`.
- `stack.md` records the thin PyQt6 front end as planned for Stage 2.

## 1. Purpose and scope

One tool, run by the CA custodian, that does:

1. **Create the CA** (`ca.key` + `ca.crt`).
2. **Issue certificates** for wearables and the fixed gateway (cloud and envelope material **Deferred**, see section 12).
3. **Write credentials to a connected ESP32-S3** over serial, with the operator choosing the port when several are connected.
4. **Deploy credentials to the gateway (Raspberry Pi) over SSH.**
5. **Registry link** (**Deferred**). Revocation is not a CA tool function: it is done through the cloud registry API.

**Out of scope:** network-exposed signing, HSM, offline signing ceremony, secure boot / flash encryption (firmware integrity is excluded project-wide), CRL distribution, mobile relay credentials (the phone is not a principal and gets no certificate).

## 2. Architecture

```
Stage 2 only:  PyQt6 GUI (thin)
               CA │ Issue │ Flash ESP │ Deploy Gateway │ Audit
                  │ calls (QThread workers)
                  ▼
Stage 1:  core/ (no Qt imports)
          ca.py  profiles.py  keys.py  flash.py  ssh.py  registry.py  audit.py  config.py
                  ▲
                  │ same functions exposed by
          cli.py  (init-ca | issue | flash | deploy | erase | audit)
```

- **Rule (Decided):** `core/` must not import Qt. CLI and GUI call the same functions, so behavior cannot diverge and the core is unit-testable headless.
- **Threading (Stage 2):** every slow or blocking operation (key generation, serial flashing, SSH) runs in a `QThread` worker and reports progress by signals.
- **Dependencies (verify versions at build time):** `cryptography`, `pyserial`, `esptool`, `esp-idf-nvs-partition-gen`, `paramiko`, `tomllib`/`tomli`. Stage 2 adds `PyQt6`. Phase "registry" adds `psycopg`.

## 3. Data layout (outside any git repo)

```
~/medmusketeer-ca/
├── config.toml                 # non-secret settings
├── ca/
│   ├── ca.key                  # passphrase-encrypted PEM, mode 600
│   ├── ca.crt
│   └── serial_db               # issued serials (audit, no secrets)
├── issued/<device_id>/
│   ├── device.key              # mode 600; deleted after successful flash (section 8)
│   ├── device.crt
│   └── meta.json               # type, key type, validity, serial, timestamps, flashed flag
├── cloud/                      # server.key, server.crt, meta.json, history/ (issue cloud)
└── audit.log.jsonl             # append-only, never contains secrets
```

`ca.key` must never be copied into the repo, onto any device, or to the gateway.

---

# STAGE 1 — CLI

## 4. Certificate profiles

| Profile | Subject CN | SAN | EKU | Key | Notes |
|---|---|---|---|---|---|
| **CA** | `MedMusketeer CA` | none | none | **EC P-256 (Decided)** | `basicConstraints CA:TRUE, pathlen:0`; `keyUsage keyCertSign, cRLSign`; **10-year validity (Decided)** |
| **Wearable (TLS client)** | `device_id` (UUIDv4) | `device_id` | clientAuth | RSA 2048 or EC P-256 (benchmarked variable; default EC P-256) | **365-day validity (Decided)** |
| **Gateway** | gateway `device_id` | `gateway.medmusketeer.local` (role SAN) + `device_id` | serverAuth **and** clientAuth | RSA 2048 or EC P-256 | serverAuth toward wearables, clientAuth toward EMQX. **365-day validity (Decided)** |
| Cloud server (EMQX mTLS listener) | `cloud.medmusketeer.local` | same | serverAuth | **EC P-256 (Implemented 2026-10-24)** | Gateway pins this CN/SAN; `keyUsage digitalSignature`; leaf validity (365 days); written to `cloud/` (`server.key` mode 600, `server.crt`, `meta.json`); `--replace` archives the old certificate under `cloud/history/<serial>/` and removes the old key |
| Cloud envelope | `cloud.medmusketeer.local` | same | none | **Deferred** | `keyUsage keyAgreement`; long-dated period Deferred |
| Wearable envelope keypair | n/a | n/a | n/a | **Deferred** | Separate EC P-256 keypair; never reuse the TLS key |

Common rules:

- The CA key type is held constant (EC P-256) across the RSA-vs-ECC leaf benchmark.
- Serial numbers: random 128-bit, recorded in `serial_db`.
- Signature hash: SHA-256.
- Before signing, the tool prints a human-readable summary of CN/SAN/EKU/key/validity so the custodian can catch mistakes.

## 5. CLI commands

```
mmca init-ca     --cn "MedMusketeer CA" [--validity-days 3650]
mmca replace-ca  ...                       # explicit typed confirmation
mmca issue       wearable [--key-type ec_p256|rsa_2048] [--device-id UUID]
mmca issue       gateway  [--key-type ec_p256|rsa_2048]
mmca issue       cloud    [--replace]          # Implemented 2026-10-24
mmca flash       --device-id UUID [--port /dev/ttyACM0]
mmca deploy      --host HOST [--port 22] [--user pi] [--restart]
mmca erase       esp|gateway ...           # clears TLS credentials and/or network settings
mmca audit       [--device-id UUID]
```

This block is the original plan, kept for reference; `mmca --help` and `tools/ca-tool/README.md` are authoritative for the implemented options.

Passphrase and sudo password are prompted interactively (never accepted as arguments or environment variables).

## 6. Workflows

### 6.1 Create CA
1. Collect CN, validity, passphrase (entered twice).
2. Generate EC P-256 key, self-sign `ca.crt`, write `ca.key` encrypted (`BestAvailableEncryption`), mode 600 from creation.
3. Print the SHA-256 fingerprint; log the event (no secrets).
4. Never store the passphrase.
5. Refuse if a CA already exists. Replacing the CA invalidates every issued cert, so it requires a separate explicit command and a typed confirmation phrase.

### 6.2 Issue (wearable)
Follows the provisioning sequence in `stack.md`: mint `device_id` → generate TLS keypair on the build machine → build CSR with CN/SAN = `device_id` → sign with `ca.key` (passphrase prompted each time) → write to `issued/<device_id>/` → record in `meta.json` and `serial_db`.

Wearable and gateway private keys are generated on the build machine (Decided in `stack.md`); on-device generation is deferred. Envelope keypair generation is **Deferred**.

### 6.3 Flash to ESP (wearable)

**Port selection**
1. List **all** serial ports with description and VID:PID (`serial.tools.list_ports`). CP210x/CH340 boards look different from native USB; ESP32-S3 native USB typically shows VID 303A.
2. Never auto-pick when more than one candidate exists. With exactly one, preselect but still require confirmation.
3. Query the chip via esptool and refuse unless it reports **ESP32-S3**. Show chip type, MAC and flash size.

**Locating the credentials partition (Decided: read from the chip)**
4. Read the partition table from the connected chip with esptool (default table location is `0x8000`; verify against the firmware's configuration), parse it, and look up the partition named **`creds`**.
5. If no `creds` partition is found: stop and write nothing, with a message that firmware containing the `creds` partition must be flashed first.
6. Check the generated image size does not exceed the partition size.

**Credential storage on the ESP (Proposed; needs firmware agreement)**
- A **dedicated, credentials-only NVS partition named `creds`**, separate from the application's `nvs`. The app NVS holds the envelope counter reservation block, `key_epoch` and mode-switch state, so a whole-NVS image written there would wipe them.
- The tool builds the image with `nvs_partition_gen` and writes it with esptool at the offset found in step 4. Firmware opens it read-only via `nvs_flash_init_partition("creds")`.
- NVS stores PEM as strings, which handles the trailing NUL that mbedTLS expects. Confirm with firmware.
- **Decided and implemented with the firmware:** partition `creds` at `0x1D0000`, 192 KB, namespace `creds`, keys `device_key`, `device_cert`, `ca_cert` (PEM strings). The firmware takes the device identifier from the certificate CN.
- **Accepted FYP-1 shortcut:** keys sit in plain flash; flash encryption and secure boot are not used (firmware integrity is out of scope).

**Write**
7. Choose the wearable from `issued/`. Warn if `meta.json` says it was already flashed.
8. Show what will be written and where; require confirmation before overwriting the `creds` region.
9. **Written now (wearable):** `device.key`, `device.crt`, `ca.crt`. Envelope key and cloud envelope cert are **Deferred**.
10. Write via esptool with progress; read back and compare a hash.
11. On verify success: mark `flashed` in `meta.json`, then **delete `device.key`** from the build machine (section 8, item 7). On verify mismatch: report loudly, do **not** mark flashed and do **not** delete.
12. Log: device_id, port, chip MAC, partition offset, timestamp, result.

### 6.4 Deploy to gateway (SSH)
1. **Inputs:** host/IP, port, username, SSH key file preferred (password allowed, never stored), remote cert dir (default `/etc/mosquitto/certs`).
2. **Host key check:** load `known_hosts`. For an unknown host, show the SHA-256 fingerprint and require explicit approval before saving. Never auto-accept. A mismatch for a known host is a hard stop.
3. **Pre-flight (local):** gateway key matches gateway cert; cert chains to `ca.crt`; role SAN `gateway.medmusketeer.local` present; cert not expired.
4. **Upload** `ca.crt`, `gateway.crt`, `gateway.key` over SFTP into a randomly named temp directory, mode 700.
5. **Install** with `sudo install -o root -g mosquitto -m 640` into the remote cert dir, then remove the temp directory. **Sudo password is prompted (Decided)**, passed without echo, never stored or logged.
6. **Verify remotely:** `openssl x509 -noout -subject -ext subjectAltName` on the installed cert; compare the fingerprint to the local one.
7. **Restart Mosquitto (Decided: restart, not reload)** when `--restart` is given, then report `systemctl is-active`. Restart is used because certificate-file pickup on reload is not confirmed; a brief connection drop is expected.
8. Log: host, files, fingerprints, result. No secrets.

**Overwrite rule:** if remote files exist, show their fingerprints, require confirmation, and back them up with a timestamp suffix.

### 6.5 Registry link (Deferred)
- Follows `stack.md`: mint the `devices` row (`pending`) before issuing, insert `device_credentials`, flip to `active` after a successful issue.
- Keep registry access behind a small `registry.py` interface with a no-registry **dry-run mode**, so everything above works without it.
- No `revoke` command (removed 2026-10-29): revocation goes through the cloud registry API, which EMQX's auth hook checks live and which updates the gateways' revocation list (`cloud-backend.md` D16).

## 7. Configuration (`config.toml`, no secrets)

```toml
[paths]
ca_dir = "~/medmusketeer-ca"

[defaults]
tls_key_type = "ec_p256"        # or "rsa_2048"
ca_validity_days = 3650
leaf_validity_days = 365

[gateway_ssh]
host = ""
port = 22
user = "pi"
remote_cert_dir = "/etc/mosquitto/certs"

[esp]
creds_partition_name = "creds"  # offset/size are read from the chip, not configured
```

## 8. Security requirements

1. `ca.key` is passphrase-encrypted, mode 600, never leaves the custodian's machine, read only during a signing action; passphrase prompted each time.
2. Passphrase, SSH password and sudo password are never written to disk, config, logs or the audit log.
3. Private keys are never displayed, logged, or included in error messages or tracebacks.
4. Private-key files are created with mode 600 from the start (not chmod after write).
5. SSH uses host key verification with explicit approval for new hosts. No auto-accept.
6. Audit log is append-only JSON lines: timestamp, action, device_id, fingerprint, result. No secrets.
7. **Key retention (Decided): `device.key` is deleted from the build machine after a successful, verified flash.** Re-flashing therefore requires re-issuing. The tool says "removed", never "securely erased": Python cannot reliably wipe data on modern filesystems. Retention of the (Deferred) envelope key follows the envelope design.
8. Wearable and gateway keys are generated on the build machine (`stack.md` decision).
9. No telemetry; no outbound network calls other than the explicit SSH (and, later, database) connections.

## 9. Error handling

- Serial port busy or missing: tell the operator to close other serial monitors, then retry.
- Chip is not ESP32-S3, or no `creds` partition found: stop before writing anything.
- Flash verify mismatch: report loudly; do not mark flashed; do not delete the key.
- SSH failure: distinguish network, host-key mismatch, auth, and sudo failures. Host-key mismatch for a known host is a hard stop.
- Any failure between "mint device_id" and "activate" leaves the device `pending` and logs the step reached.

## 10. Testing

- **Unit (headless, `core/` only):** profile contents (CN, SAN, EKU, key usage, pathlen), chain verification against `ca.crt`, key/cert match, serial uniqueness, encrypted-key round trip, partition-table parsing against a sample binary.
- **Interop:** generated gateway and wearable certs complete the Mosquitto mTLS handshake; this also feeds the pending CN-to-username ACL verification on the Pi.
- **ESP:** test on a real ESP32-S3 with a scratch `creds` partition first.
- **SSH:** test against a throwaway Pi or VM first.

## 11. Stage 1 build order

1. Core + `init-ca` + `issue` (output is files on disk).
2. `flash` (port selection, chip check, partition lookup, write, verify, key removal).
3. `deploy` (SSH).
4. `audit`; registry-link stub with dry-run mode.

---

# STAGE 2 — PyQt6 GUI

## 12. GUI layout

Thin tabbed window over the Stage 1 core, with a persistent log pane at the bottom showing progress (never key material).

| Tab | Function |
|---|---|
| **CA** | Shows CA status (subject, fingerprint, expiry). Create CA form: CN, validity, passphrase twice. Disabled once a CA exists; a separate "replace CA" action requires typing a confirmation phrase. |
| **Issue** | Pick type (wearable / gateway), key type, validity. `device_id` auto-minted, editable only in an "advanced" expander. Shows planned CN/SAN/EKU before signing; passphrase prompted at signing time. |
| **Flash ESP** | Port list with refresh, chip check, detected `creds` partition offset/size, wearable selector, flash button. |
| **Deploy gateway** | Host, port, user, auth method, remote paths; test connection; host-key approval dialog; sudo password prompt; "restart Mosquitto" checkbox. |
| **Audit** | Read-only view of `audit.log.jsonl` with filter by device_id. |

- Every destructive or irreversible action (replace CA, overwrite flash region, overwrite remote files, delete key after flash) uses a confirmation dialog stating exactly what will change.
- Workers: each core call runs in a `QThread`; the GUI thread never blocks.
- Testing: smoke-test each tab with mocked core calls.

---

## 13. Deferred (to be addressed later)

- **Envelope keys:** wearable envelope keypair, cloud envelope cert/key, their validity periods and retention, and the extra flash payload items.
- **Cloud keys:** EMQX server cert profile, key type and validity.
- **Registry link:** how the tool registers issued devices and credentials in the cloud registry.
- **Uplink bridge credentials:** whether the bridge needs its own copy of `gateway.key` and `ca.crt` with different ownership, and where (one uplink per gateway, so likely a small detail).

## 14. Open items

- Stage 2 GUI (not started).
- Registry link (the registry API exists since Iteration 3).
- Envelope keys and the cloud certificate profiles (section 13).
- ACL denial checks on the Pi itself (CN-to-username already observed there; denials verified on a container broker).
- Resolved: the `creds` NVS names and PEM-string handling are agreed with the firmware and implemented; the partition table is read from the chip; certificate replacement on the Pi was exercised in the hardware procedures (`pi_cert_backup_restore.txt`).
