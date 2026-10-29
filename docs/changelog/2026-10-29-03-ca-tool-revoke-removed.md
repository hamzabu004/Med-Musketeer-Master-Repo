# CA tool: the planned `revoke` command is removed

- **Date:** 2026-10-29
- **Type:** decision
- **Module:** M1 CA tool
- **Commits:** see `git log -- docs/decisions/ca-tool-spec.md`

## What changed
- `mmca revoke`, deferred since the CA tool spec, is removed from the plan. It was never built, so no code changes.
- Revocation is done only through the cloud registry API and the dashboard (`/admin/devices/{id}/revoke`, `/admin/credentials/{id}/revoke`).
- The CA tool's registry link (registering issued devices and credentials) stays deferred, unchanged.
- **Docs:**
  - `ca-tool-spec.md`: scope, architecture, command list, section 6.5, GUI tabs, deferred and open items.
  - `stack.md`, `gaps.md`, `iteration-3-cloud.md`, `iteration-4-revocation-sync.md`.

## Why
The registry is the single source of revocation: EMQX checks it live for gateways, and it drives the gateways' wearable revocation list (`cloud-backend.md` D16). A second revocation entry point in a local tool would duplicate that, and it could not reach the cloud from the custodian's machine without network access the tool deliberately does not have.

## Evidence
None (docs only).
