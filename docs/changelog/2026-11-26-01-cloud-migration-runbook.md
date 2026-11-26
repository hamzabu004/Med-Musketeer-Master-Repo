# Procedure for moving the cloud stack to another server

- **Date:** 2026-11-26
- **Type:** docs
- **Module:** M7 cloud
- **Commits:** pending

## What changed
- `cloud/cloud-migration.md` describes how to move the public deployment off the Oracle VM: which state has to move (above all `cloud/.env`, whose ZITADEL masterkey the data depends on), copying the volumes as they are or restoring a dump when the CPU architecture changes, the DNS switch, the deploy settings that name the server (`DEPLOY_*` secrets, the `opc` user in `deploy.yml`), checks, and rollback.
- `cloud/README.md` links to it from "Server set-up".

## Why
To make moving to another provider possible without working it out again, and without losing data.

## Evidence
None: the procedure has not been carried out.
