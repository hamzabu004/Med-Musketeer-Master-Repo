# Continuous ECG streaming only on demand

- **Date:** 2026-10-23
- **Type:** decision
- **Module:** M2 firmware, M5 gateway, M7 cloud
- **Commits:** ccacc85

## What changed
- The `telemetry` topic carries only on-demand recordings: continuous ECG is streamed after a doctor's request command, for that recording. Otherwise only screening-triggered alerts (on `alert`) leave the wearable.
- The FYP-1 benchmark is a fixed-vs-mobile path comparison; the earlier path × transmission-mode 2×2 is dropped.
- Still open: how an on-demand stream starts and stops (request fields, fixed duration vs explicit stop, `command_ack`).

## Why
Confirmed by the team; it settles what the `telemetry` topic carries under ADR-1.

## Evidence
None (decision). Recorded in `stack.md`, `mqtt-fixed-path-topics.md`, `scope.md` and `gaps.md`.
