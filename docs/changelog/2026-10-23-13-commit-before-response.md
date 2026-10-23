# API commits before it responds (review finding 1 fixed)

- **Date:** 2026-10-23
- **Type:** code
- **Module:** M7 cloud
- **Commits:** see `git log -- cloud/backend/app/db.py`

## What changed
- `Conn` now uses `Depends(connection, scope="function")`, so each request's transaction commits before the response is sent.
- The error handling now also covers the commit, so a write rejected at commit returns an error (422) instead of success.

## Why
Slice 2 review finding 1: the API could answer 201 before committing, and a failed commit was never reported to the client. Fixed now rather than in the testing phase because the Slice 3 endpoints build on the same connection.

## Evidence
New test `test_a_write_that_fails_at_commit_is_not_reported_as_success` (a deferred constraint trigger fails at commit) failed before the fix and passes after; 25 unit, schema and registry tests pass.
