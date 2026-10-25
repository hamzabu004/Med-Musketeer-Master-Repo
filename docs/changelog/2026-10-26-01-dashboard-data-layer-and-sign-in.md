# Dashboard data layer, sample-data mode and ZITADEL sign-in (dashboard Phase 3)

- **Date:** 2026-10-26
- **Type:** code
- **Module:** M8 dashboard
- **Commits:** see `git log -- web/dashboard/` on `feat/dashboard`

## What changed
- **Data-source contract** (`src/services/contracts.ts`): one method per cloud endpoint, grouped as the registry (system admin), org (org admin), patients/devices, and care (ECG, alerts). Types are aliases of the generated OpenAPI schema.
- **API implementation:**
  - `fetch` with the bearer token;
  - a 401 renews the token once (refresh token) and retries;
  - error answers become `ApiError`, which reads every `detail` shape: string, `{error, constraint}`, or a validation list;
  - user messages treat a 404 as "not found, or not available to you" (D9 does not tell the two apart).
- **Sample-data implementation** (`src/services/mock/`):
  - the same people, devices, alerts and synthetic ECG as `seed-dev`, plus a second organisation;
  - it applies the API's D9 rules (403 for a role, 404 out of reach) and state rules (credential before activation, revoke cascades, wearable issue checks, disable consequences, acknowledge once, invite code shown once);
  - kept in `sessionStorage`, reset on sign-out.
- **Mode flag:**
  - `NEXT_PUBLIC_DATA_SOURCE=api|mock`, with `NEXT_PUBLIC_API_URL`;
  - `src/config/capabilities.ts` marks on-demand ECG, attack tests and alert push as not served by the API yet;
  - the modes are never mixed, and sample mode shows "Sample data" in the header.
- **Sign-in** (`oidc-client-ts`):
  - settings from `GET /auth/config`; authorization code + PKCE; `/auth/callback`;
  - automatic renewal with the refresh token;
  - sign-out through ZITADEL's end-session, which ends the ZITADEL session too;
  - tokens in `sessionStorage` only.
- **Session:**
  - the role comes from `/me`;
  - an account ZITADEL accepts but the API refuses gets a "no access" page with sign-out;
  - a server that cannot be reached, or one without the dashboard app, gets an explanation.
- **Pages:**
  - sign-in (ZITADEL button, or the sample accounts in sample mode), which sends a signed-in user to their dashboard (Phase 2 review finding 2);
  - the callback;
  - invite-code help (`/invite`);
  - the "not a medical device" notice on the pages outside the shell.
- **ECG:** `src/lib/ecg.ts` decodes the API's int16le-base64 chunks and stitches them by `seq`.
- **`gen:api`** also saves `src/api/openapi.json`; a unit test checks every API call against it.
- **API-mode browser tests:** `scripts/api-e2e.sh` brings up the cloud under its own compose project and ports, seeds it with `seed-dev`, runs the tests and removes the stack.

## Why
Phase 3 of the dashboard rebuild: the screens (Phases 4–6) need sign-in, a role, and one data interface that works against the cloud and, for a deployment without the cloud, against sample data that behaves the same way.

## Evidence
`docs/testing/evidence/2026-10-26/dashboard/`:
- `checks.txt`: typecheck, lint, 70 unit tests, production build. The tests cover:
  - error mapping and the HTTP client (refresh and retry);
  - every API call against the OpenAPI document;
  - the sample data's D9 and state rules;
  - ECG decoding;
  - the role guard.
- `e2e-mock.txt`: 22 browser tests, desktop and phone. Each role lands in its own area and is kept out of the others; sign-in and sign-out; no horizontal scroll.
- `e2e-api.txt`: 6 browser tests against a real stack:
  - each of the four seeded roles signs in through ZITADEL's login and lands by the role `/me` reports;
  - tokens are not in `localStorage`;
  - the doctor's API calls pass CORS and D9 (5 alerts, `/accounts` 403);
  - signing out ends the ZITADEL session.

## Noticed
ZITADEL's login page offers "Register new user". A self-registered user gets no project role, so the API refuses them and the dashboard shows "no access". Whether to turn self-registration off in the bootstrap is a cloud decision, not made here.
