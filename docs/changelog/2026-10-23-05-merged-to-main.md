# Firmware fix and post-report work merged into main

- **Date:** 2026-10-23
- **Type:** ops
- **Module:** project
- **Commits:** main fast-forwarded from ad41289 to ccacc85

## What changed
`main` now contains the SNTP retry fix (4eac878, previously only on `fix/firmware-sntp-retry`) and the commits in entries 01 to 04. The branches `fix/firmware-sntp-retry` and `test/report-evidence` are pushed and fully merged.

## Why
So the public master repository holds the tests, evidence, app and context that the work depends on.

## Evidence
`git log origin/main`.
