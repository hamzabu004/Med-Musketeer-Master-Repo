# Project context consolidated in docs/decisions

- **Date:** 2026-10-23
- **Type:** docs
- **Module:** project
- **Commits:** fc10333

## What changed
- `docs/decisions/` is now the single home of the project context: `scope.md`, `stack.md`, `gaps.md`, `mqtt-fixed-path-topics.md`, `ca-tool-spec.md`, and a `README.md` index. The copies in `FYP/COntexts/` were deleted.
- The gateway Mosquitto setup script moved to `tools/Fixed-Gateway-Setup/setup_mosquitto.sh`.
- The content was brought in line with the mid report: two research strands, four human roles and organisations, measured results so far, the cloud schema summary and access rules, what is implemented, the second Pi as the first cloud server, and the open design items.
- Field names follow the report's schema: `ecdh_envelope`, `is_testbed`, `credential_ref`.

## Why
The context existed in two places and was older than the mid report (`GAPS.md` dated from 2026-09-26).

## Evidence
None (documentation).
