# Cloud stack skeleton (Iteration 3, Slice 1)

- **Date:** 2026-10-23
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/`

## What changed
- `cloud/compose.yaml` with pinned images (all with amd64 and arm64 builds): `timescale/timescaledb:2.31.0-pg18`, `ghcr.io/zitadel/zitadel:v4.20.0` and `zitadel-login:v4.20.0`, `traefik:v3.7.16`, `emqx/emqx:6.3.2`, and the API built on `python:3.14.9-slim-trixie`. Published ports bind to 127.0.0.1.
- PostgreSQL 18 instead of the planned 17 (newest TimescaleDB; ZITADEL v4 supports 14–18). ZITADEL v4 needs a separate Login UI container and one HTTP origin, so Traefik routes to both from a static file (no container-engine socket mounted).
- `postgres/init/010-databases.sh` creates the `zitadel` and `medmusketeer` databases and the roles `zitadel`, `mm_migrator`, `mm_api`; TimescaleDB is enabled in `medmusketeer`.
- `scripts/init-env.sh` generates `.env` with random secrets and refuses to overwrite one (the ZITADEL masterkey cannot change after initialisation).
- FastAPI app (`cloud/backend/`): `/livez`, and `/healthz` checking the database (with the TimescaleDB extension), ZITADEL and EMQX; settings from `MM_*` variables, startup fails without them. Dependencies pinned in `requirements.lock`.
- `cloud/run_cloud_tests.sh` stores evidence; TC-C01 and TC-C02 added to `docs/testing/test_traceability.md`.

## Why
Slice 1 of `docs/iterations/iteration-3-cloud.md`: a stack every later slice builds on.

## Evidence
9 tests pass (TC-C01 against the full stack from empty volumes, TC-C02, and `/livez`/`/healthz` unit tests); evidence in `docs/testing/evidence/2026-10-23/cloud/`. Idle memory on the laptop: EMQX 342 MiB, Postgres 160 MiB, ZITADEL API 85 MiB, API 79 MiB, Login UI 75 MiB, Traefik 21 MiB (about 760 MiB in total).

## Notes
- Docker Desktop on Linux shares only `/home` by default; the repository's drive (`/run/media/hmz-gul/01DB003D88B96CA0`) had to be added under Settings → Resources → File sharing, or bind mounts arrive empty.
- `fastapi.testclient` warns that `httpx` with Starlette's test client is deprecated in favour of `httpx2`; harmless for now.
