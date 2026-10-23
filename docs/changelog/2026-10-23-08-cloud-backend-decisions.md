# Cloud backend decisions D1–D10 taken; EMQX 6.3.2 pinned

- **Date:** 2026-10-23
- **Type:** decision
- **Module:** M7 cloud
- **Commits:** see `git log -- docs/decisions/cloud-backend.md`

## What changed
Added `docs/decisions/cloud-backend.md` with the Iteration 3 Slice 0 decisions, all Decided:
- D1 `attested_by` comes from the broker: an EMQX rule republishes gateway messages to `ingest/{username}/{topic}`, readable only by the adapter.
- D2/D3 roles are ZITADEL project roles; one ZITADEL organisation per client organisation; `users` and a new `organisations.zitadel_org_id` column mirror them, changed only through the API.
- D4 gateways authenticate with mTLS (cert CN as username) plus an HTTP authentication hook checking the registry.
- D5 gateway ACL; wearable↔gateway assignment is observe-only for now.
- D6 alert payload v1; D7 normalised ingestion message `ingest-v1`; D8 SQLAlchemy 2 Core + Alembic + psycopg 3.
- D9 role × endpoint matrix: the organisation admin cannot read patient ECG data; a doctor sees the live status of their patients' devices and reads their disorders.
- D10 EMQX pinned at `emqx/emqx:6.3.2` (newest, released 2026-10-16; amd64 and arm64).

`stack.md`, `gaps.md`, the decisions index and the Iteration 3 plan point to the new file.

## Why
These decisions blocked Iteration 3 code. The team confirmed the proposals and answered the three open cells of the role matrix. EMQX 5.9 and later use the Business Source License 1.1; its grant allows single-node production use and academic use, which covers this project.

## Evidence
EMQX licence: `LICENSE` at tag 6.3.2 in github.com/emqx/emqx. Image architectures: Docker Hub tag `emqx/emqx:6.3.2`. Features (`peer_cert_as_username`, HTTP authentication results, rule Republish) from docs.emqx.com.
