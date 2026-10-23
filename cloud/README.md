# Cloud backend

The MedMusketeer cloud platform (M7), built in Iteration 3 (`docs/iterations/iteration-3-cloud.md`). Design decisions: `docs/decisions/cloud-backend.md` and `docs/decisions/stack.md`.

## Services

| Service | Image | Role | Host port (127.0.0.1) |
|---|---|---|---|
| `postgres` | `timescale/timescaledb:2.31.0-pg18` | Databases `medmusketeer` (TimescaleDB) and `zitadel` | — |
| `zitadel-api` | `ghcr.io/zitadel/zitadel:v4.20.0` | Human IAM (OIDC) | via `proxy` |
| `zitadel-login` | `ghcr.io/zitadel/zitadel-login:v4.20.0` | ZITADEL Login UI | via `proxy` |
| `proxy` | `traefik:v3.7.16` | One HTTP origin for ZITADEL's API and Login UI | 8080 |
| `emqx` | `emqx/emqx:6.3.2` | MQTT broker (gateway listener added in Slice 4) | 18083 (dashboard) |
| `api` | built from `backend/` (Python 3.14) | MedMusketeer API | 8000 |

Every image is pinned to an exact version with amd64 and arm64 builds, so the same file runs on the cloud Pi. Upgrading an image is a deliberate change with a change-log entry.

Database roles, created on an empty volume by `postgres/init/010-databases.sh`: `zitadel` (owns `zitadel`), `mm_migrator` (owns `medmusketeer`, runs the migrations), `mm_api` (the API's runtime login).

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

## API endpoints so far

| Path | Meaning |
|---|---|
| `GET /livez` | The process is up (used by the container health check) |
| `GET /healthz` | Database (with the TimescaleDB extension), ZITADEL and EMQX reachable; 503 if any is not |

## Tests

```bash
cd cloud/backend
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/pip install --no-deps -e . && .venv/bin/pip install pytest pytest-cov
.venv/bin/python -m pytest -m "not integration"   # unit tests, no containers
../run_cloud_tests.sh                               # all tests + evidence in docs/testing/evidence/<date>/cloud/
```

The integration tests (TC-C01) bring the stack up under the compose project `mm-cloud-tc` on ports 18080/18000/28083 and remove it afterwards, so a running development stack is not affected. Set `MM_COMPOSE="podman compose"` to use Podman.

## Dependencies

`backend/requirements.lock` is generated from `pyproject.toml` with hashes, and the image installs it with `--require-hashes`. After changing a dependency:

```bash
pip install pip-tools
pip-compile --generate-hashes --strip-extras --allow-unsafe --output-file backend/requirements.lock backend/pyproject.toml
```
