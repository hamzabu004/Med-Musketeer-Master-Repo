# Dashboard sign-in, CORS, name directory and development data (dashboard Phase 1)

- **Date:** 2026-10-25
- **Type:** code
- **Module:** M7 cloud, M8 dashboard
- **Commits:** see `git log -- cloud/` on `feat/dashboard`

## What changed
- **Dashboard OIDC app:** the `zitadel-bootstrap` job creates "MedMusketeer Dashboard" in the MedMusketeer project:
  - a browser app (authorization code + PKCE, no secret, refresh tokens);
  - JWT access tokens with the roles asserted;
  - redirect URIs from the new `DASHBOARD_ORIGINS` setting (default `http://localhost:3000`).

  Its client id is written to `zitadel.json`.
- **`GET /auth/config`** (public): the issuer, client id, project id and the scopes a dashboard login must request.
- **CORS:** `MM_CORS_ORIGINS` (set from `DASHBOARD_ORIGINS` by compose). Bearer tokens only, no credentials.
- **`GET /directory`:** names from ZITADEL for the accounts the caller works with.
  - org admin: whole org, with e-mail;
  - doctor: self and own patients;
  - patient: self and own doctor;
  - system admin: refused.

  Profiles are cached for 60 s.
- **`python -m app.manage seed-dev`:** development data on an empty stack.
  - Seven ZITADEL human users across the four roles, sharing one printed password.
  - "Dev Hospital" with a gateway and wearables.
  - Alert segments of synthetic ECG (360 Hz) with classifications and alerts, and IDS events.
- **Start order fix:** EMQX now starts after the API is healthy (`compose.yaml`), and its entrypoint also waits for the API's `/livez` (Docker's restarts ignore `depends_on`); the API no longer waits for EMQX.
  - Before, EMQX started first and could not resolve `api`, so its HTTP authenticators stayed down until their next health check (about 15 s) and refused every client.
  - The longer bootstrap made this window long enough to fail TC-C14 and TC-C17 in two runs (the adapter monitor was refused).
  - The API needed EMQX only for `/healthz`, which still reports it.
- **Decisions:** D14 added to `cloud-backend.md`; D9 gains the directory row. In `gaps.md`, the "API returns no names" gap is resolved.

## Why
Phase 1 of the dashboard rebuild (the POC-Lite proof of concept is being replaced by `web/dashboard`, grounded in the cloud API). A browser app could not sign in or call the API before this:
- there was no OIDC app and no CORS;
- it could not show people's names, which live only in ZITADEL;
- with ingestion (Slice 5) not built, it had no data to show.

## Evidence
317 cloud tests pass (`docs/testing/evidence/2026-10-25/cloud/`). TC-C19 signs in each seeded role through the dashboard app, scripting the browser's steps (PKCE authorization request, password session, linking the session to the request, code exchange). It then checks `/me`, the CORS headers, the directory names and the seeded ECG (`stack/tc_c19_dashboard_sign_in.json`).

New tests:
- `test_directory` (role visibility, missing profiles, ZITADEL failure);
- the `GET /directory` row in TC-C09;
- CORS and `/auth/config` unit tests;
- the bootstrap's app creation and update;
- profile batching and caching.

## Review
`/code-review high` found ten issues (`docs/testing/review-findings/2026-10-25-dashboard-phase-1-cloud-enablers.md`); seven are fixed in a follow-up commit:
- seed-dev deletes what it created in ZITADEL when it fails;
- expired profiles are evicted;
- http and https dashboard origins can no longer be mixed (dev mode);
- only ZITADEL's "No changes" reply is ignored;
- EMQX waits for the API on every start;
- one shared origin parser;
- the seed no longer mutates module state.
