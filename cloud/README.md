# Cloud backend

The MedMusketeer cloud platform (M7), built in Iteration 3 (`docs/iterations/iteration-3-cloud.md`). Design decisions: `docs/decisions/cloud-backend.md` and `docs/decisions/stack.md`.

## Services

| Service | Image | Role | Host port (127.0.0.1) |
|---|---|---|---|
| `postgres` | built from `postgres/` on `timescale/timescaledb:2.31.0-pg18` | Databases `medmusketeer` (TimescaleDB) and `zitadel` | — |
| `zitadel-api` | `ghcr.io/zitadel/zitadel:v4.20.0` | Human IAM (OIDC) | via `proxy` |
| `zitadel-login` | `ghcr.io/zitadel/zitadel-login:v4.20.0` | ZITADEL Login UI | via `proxy` |
| `proxy` | built from `traefik/` on `traefik:v3.7.16` | One HTTP origin for ZITADEL's API and Login UI | 8080 |
| `emqx` | built from `emqx/` on `emqx/emqx:6.3.2` | MQTT broker: gateway mTLS listener, internal service listener, hooks to the API, republish rule | 8883 (gateways), 1883 (services), 18083 (dashboard) |
| `api` | built from `backend/` (Python 3.14) | MedMusketeer API | 8000 |

Every image is pinned to an exact version with amd64 and arm64 builds, so the same file runs on the cloud Pi. Upgrading an image is a deliberate change with a change-log entry.

Configuration is built into the `postgres`, `proxy` and `emqx` images, not bind-mounted: Docker Desktop's file sharing for the repository's drive proved unreliable (stale mount paths), and baked-in config behaves the same on the Pi. Rebuild after editing it (`docker compose up -d --build`). Database roles, created on an empty volume by `postgres/init/010-databases.sh` (copied into the `postgres` image): `zitadel` (owns `zitadel`), `mm_migrator` (owns `medmusketeer`, runs the migrations), `mm_api` (the API's runtime login).

## Run

```bash
cd cloud
scripts/init-env.sh            # writes .env with random secrets; never commit it
docker compose up -d --wait --build
curl -s http://127.0.0.1:8000/healthz
```

- ZITADEL: http://localhost:8080 (first admin `zitadel-admin@zitadel.localhost`, password `ZITADEL_ADMIN_PASSWORD` in `.env`).
- EMQX dashboard: http://127.0.0.1:18083 (user `admin`, password `EMQX_DASHBOARD_PASSWORD`).
- Keep `.env`: the ZITADEL masterkey cannot change once ZITADEL has been initialised with it. To start from scratch, `docker compose down --volumes` and delete `.env`.
- A `.env` made before Slice 4 needs `EMQX_HOOK_SECRET`, `EMQX_ADAPTER_PASSWORD` and `EMQX_NODE_COOKIE` (random letters and digits; see `scripts/init-env.sh`).

## EMQX gateway listener

Gateways connect with mutual TLS on port 8883 (`docs/decisions/cloud-backend.md` D1, D4, D5, D13). The listener needs the cloud server certificate from the CA tool; until it is installed, EMQX runs with the listener off and logs a warning.

```bash
mmca issue cloud                              # once a year: mmca issue cloud --replace
cloud/scripts/install-emqx-certs.sh           # reads ~/medmusketeer-ca; restarts EMQX if running
```

- A gateway connects only if its certificate chains to the MedMusketeer CA and is registered as an active `x509_mtls` credential (its SHA-256 fingerprint, as `mmca issue` prints it) of an active `fixed_gateway`. Register it as the system admin: `POST /admin/devices`, `POST /admin/devices/{id}/credentials` with `credential_ref` = the fingerprint, `POST /admin/devices/{id}/activate`.
- Gateways verify the cloud as `cloud.medmusketeer.local` (CN/SAN pin), whatever address they connect to.
- Gateway messages are republished to `ingest/{gateway id}/{topic}` for the adapter (`mm-adapter` on the internal listener, password `EMQX_ADAPTER_PASSWORD`).
- On the cloud Pi, set `EMQX_GATEWAY_BIND_ADDRESS` to its Tailscale address.

## API endpoints so far

| Path | Meaning |
|---|---|
| `GET /livez` | The process is up (used by the container health check) |
| `GET /healthz` | Database (with the TimescaleDB extension), ZITADEL and EMQX reachable; 503 if any is not |
| `GET /me` | The caller's user id, role, organisation and (patients) patient id |
| `/admin/...` | System admin: organisations and their admins, devices, credentials, device grants, registry audit log, security events |
| `/organisation`, `/devices`, `/audit` | Own organisation, its devices (doctor: their patients' wearables), its audit log (org admin) |
| `/accounts` | Org admin: create (in ZITADEL and `users`, returns an invite code), list, disable doctor and patient accounts |
| `/patients/...` | Org admin: patients, doctor assignment, wearable issue/return, disorders, exports. Doctor: their patients and disorders |
| `/alerts`, `/patients/{id}/alerts`, `/patients/{id}/segments`, `/segments/{id}` | Doctor (own patients) and patient (self): alerts, acknowledgement (doctor), ECG segments with samples |
| `/internal/emqx/...` | EMQX's authentication and authorisation hooks; only with the shared `EMQX_HOOK_SECRET`, not in the API description |

Every endpoint except `/livez` and `/healthz` needs `Authorization: Bearer <ZITADEL access token>`: a JWT for the MedMusketeer project, from an active user registered in `users` with the same role (`app/auth.py`). Who may call what is the D9 matrix in `docs/decisions/cloud-backend.md`, tested in full by TC-C09. The interactive API description is at http://127.0.0.1:8000/docs.

## ZITADEL set-up

The one-off `zitadel-bootstrap` job runs on every `up`. With the IAM_OWNER service account `mm-bootstrap` (created on ZITADEL's first start; its token stays in the `zitadel-bootstrap` volume, which the API does not mount), it creates the `MedMusketeer` project and its roles `system_admin`, `org_admin`, `doctor`, `patient`, grants `system_admin` to ZITADEL's first admin, and writes `zitadel.json` (issuer, project id, default organisation id) to the `mm-config` volume for the API.

It also creates the API's own service account `mm-api` with the instance role `IAM_ORG_MANAGER` and writes its token to the `mm-secrets` volume (mounted read-only by the API, mode 0600). The API uses it to create organisations, organisation admins, doctors and patients in ZITADEL. The token is valid for a year; the job replaces it when it is missing or no longer works, and the API reloads it when ZITADEL refuses the old one. Without it, account and organisation creation answer 503.

New accounts get no password: the API returns an invite code once, which the person redeems in ZITADEL's login to set their own credentials.

Register the first admin as the MedMusketeer system admin once; the job's log prints the exact command:

```bash
docker compose logs zitadel-bootstrap | grep register-user
docker compose exec api python -m app.manage register-user --zitadel-sub <id> --role system_admin
```

The service account is configured only on ZITADEL's first start. A stack created before it was added needs `docker compose down --volumes` (which deletes all data) to pick it up.

## Tests

```bash
cd cloud/backend
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/pip install --no-deps -e . && .venv/bin/pip install pytest pytest-cov paho-mqtt
.venv/bin/python -m pytest -m "not integration"   # unit tests, no containers
../run_cloud_tests.sh                               # all tests + evidence in docs/testing/evidence/<date>/cloud/
```

The stack tests (TC-C01, C12 to C18) bring the stack up once under the compose project `mm-cloud-tc` on ports 18080/18000/28083/28883/21883, with a throwaway CA made by the CA tool in `tools/ca-tool/`, and remove it afterwards, so a running development stack is not affected. Set `MM_COMPOSE="podman compose"` to use Podman.

## Dependencies

`backend/requirements.lock` is generated from `pyproject.toml` with hashes, and the image installs it with `--require-hashes`. After changing a dependency:

```bash
pip install pip-tools
pip-compile --generate-hashes --strip-extras --allow-unsafe --output-file backend/requirements.lock backend/pyproject.toml
```
