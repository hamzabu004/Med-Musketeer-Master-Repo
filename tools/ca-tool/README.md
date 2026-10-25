# MedMusketeer CA Tool

Local CA and provisioning CLI for the FYP-1 MQTT+TLS baseline. The CLI and core run on the custodian's machine; the CA private key is never sent to a device or gateway.

## Install

Use Python 3.11 or later in a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install -e . --no-deps
```

The default data directory is `~/medmusketeer-ca`. Override it with the global `--root` option for a separate test CA.

The generated `config.toml` contains the default leaf key type, validity periods, ESP credentials partition name, and non-secret gateway SSH settings. No password or passphrase belongs in that file.

## Commands

```text
mmca init-ca [--cn TEXT] [--validity-days DAYS]
mmca replace-ca --confirm-phrase 'REPLACE MEDMUSKETEER CA'
mmca issue wearable [--device-id UUID] [--key-type ec_p256|rsa_2048] [--validity-days DAYS]
mmca issue gateway [--device-id UUID] [--key-type ec_p256|rsa_2048] [--validity-days DAYS]
mmca issue cloud [--validity-days DAYS] [--replace]
mmca flash --device-id UUID [--port PORT]
mmca deploy --device-id UUID --host HOST [--port 22] [--user pi] [--remote-cert-dir PATH] [--restart]
mmca erase esp tls|network|all --device-id UUID [--port PORT]
mmca erase gateway --device-id UUID --host HOST [--port 22] [--user pi] [--remote-cert-dir PATH]
mmca audit [--device-id UUID]
```

Passphrases and sudo credentials are prompted without echo and are never accepted as command arguments or environment variables. New SSH host keys require explicit approval; mismatches against known hosts stop deployment.

## Provision an ESP32 and Mosquitto gateway

Run the commands below in order from the CA Tool environment. Replace the example UUIDv4 values with unique IDs for your ESP32 and broker gateway. Replace `/dev/ttyACM0` with the ESP32 serial port and `192.168.1.20` with the broker host address.

```sh
ESP_ID=8f0f5194-93bf-4e1d-8e72-f96fa1f3df21
GATEWAY_ID=64e33c48-5c41-4afe-8772-e937e51d67a0
BROKER_HOST=192.168.1.20

# Create the self-signed CA and its encrypted private key. Do this once.
mmca init-ca

# Issue a client certificate for the ESP32, then flash its creds partition.
mmca issue wearable --device-id "$ESP_ID"
mmca flash --device-id "$ESP_ID" --port /dev/ttyACM0

# Issue the broker gateway certificate, then deploy its files over SSH.
mmca issue gateway --device-id "$GATEWAY_ID"
mmca deploy --device-id "$GATEWAY_ID" --host "$BROKER_HOST" --user pi --restart
```

`init-ca` prompts for the CA passphrase. Each `issue` command previews the certificate and prompts for confirmation and the CA passphrase. `flash` asks before rep
lacing the ESP32 `creds` partition and removes the local ESP32 private-key file only after read-back verification succeeds. On first SSH connection, verify and approve the host-key fingerprint; deployment also asks before backing up and overwriting existing remote files.

Configure Mosquitto to use the deployed certificate files and require client certificates before using `--restart`; `deploy` installs credentials but does not configure the broker listener. The ESP-COM firmware defines the dedicated `creds` NVS partition and reads its certificate values for MQTT mTLS. Flashing writes only this partition. The private key in device flash is not protected by flash encryption, and removing its local file is not secure erasure.

## Cloud server certificate

`mmca issue cloud` issues the server certificate of the cloud's EMQX gateway listener: CN and SAN `cloud.medmusketeer.local` (the name gateways pin), serverAuth only, EC P-256, signed by the same CA. The files go to `cloud/` in the data directory (`server.key` mode 600, `server.crt`, `meta.json`). An existing certificate is replaced only with `--replace`; the old certificate and metadata move to `cloud/history/<serial>/` and the old key is removed. Install it with `cloud/scripts/install-emqx-certs.sh` from the repository.

Every certificate carries key identifiers (SKI and AKI), which strict TLS clients such as Python 3.13+ require. A CA created before 2026-10-24 has no SKI; chains from it fail strict verification until the CA is replaced.

## Erase device credentials

The ESP-COM firmware stores Wi-Fi and MQTT broker settings, Wi-Fi driver state, and BLE bonds in the ordinary application `nvs` partition, and TLS material in the separate `creds` partition. `erase esp` works over USB serial with esptool. It checks the ESP32-S3 identity and the MAC recorded at flash time, erases the selected partitions, and verifies that they read back blank. The chip stays in its bootloader until verification finishes, then resets once. Each scope requires its own typed phrase:

| Scope | Erases | Phrase |
|---|---|---|
| `tls` | `creds` partition only | `ERASE ESP TLS CREDENTIALS` |
| `network` | application `nvs` partition: Wi-Fi SSID and password, MQTT broker host and port, Wi-Fi driver state, BLE bonds | `ERASE ESP NETWORK SETTINGS` |
| `all` | both partitions | `ERASE ESP TLS AND NETWORK` |

```sh
mmca erase esp tls --device-id "$ESP_ID" --port /dev/ttyACM0
mmca erase esp network --device-id "$ESP_ID" --port /dev/ttyACM0
mmca erase esp all --device-id "$ESP_ID" --port /dev/ttyACM0
```

After `tls` or `all`, flash a new wearable identity with `mmca flash` before MQTT can connect. After `network` or `all`, the gateway boots to its QR code and waits for BLE provisioning. Because BLE bonds are erased too, remove the old pairing on the phone before pairing again. The partition names can be changed with `creds_partition_name` and `app_nvs_partition_name` in the `[esp]` section of `config.toml`.

`erase gateway` removes `ca.crt`, `gateway.crt`, `gateway.key`, and their CA Tool deployment backups from the configured remote certificate directory. It stops Mosquitto first if the service is running, and leaves its configuration, ACL files, and service password in place. Restarting Mosquitto requires deploying gateway certificates again. The SSH host-key checks still apply, and the command requires the typed phrase `ERASE GATEWAY TLS CREDENTIALS`:

```sh
mmca erase gateway --device-id "$GATEWAY_ID" --host "$BROKER_HOST" --user pi
```

## Development checks

```sh
pytest
```

Hardware acceptance still requires an ESP32-S3 with a scratch `creds` partition, plus a throwaway Mosquitto gateway/VM for mTLS and SSH deployment checks.
