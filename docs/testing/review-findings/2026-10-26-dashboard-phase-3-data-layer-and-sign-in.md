# Code review findings — dashboard Phase 3 (data layer, sample-data mode, ZITADEL sign-in)

- **Reviewed:** commit `9aad358` on `feat/dashboard`, `/code-review high`, 2026-10-26
- **Status:** all 10 fixed.
- **Verified:** typecheck, lint, 74 unit tests, build, 22 sample-mode and 6 API-mode browser tests pass after the fixes (`docs/testing/evidence/2026-10-26/dashboard/`).

| # | Severity | File | Finding | Failure scenario | Outcome |
|---|---|---|---|---|---|
| 1 | Low | `src/api/errors.ts` | `statusText ?? …` never fell back: HTTP/2 sends an empty status text. | A 4xx without `detail` behind an HTTP/2 proxy shows an empty error. | **Fixed** (`\|\|`). Test added. |
| 2 | Medium | `src/auth/session.tsx` | A failed renewal left the state `signedIn`. | After the refresh token expires, every screen shows 401 errors and nobody is sent to sign in. | **Fixed.** A failed renewal or a silent-renew error moves the state to signed out with "Your session has ended". |
| 3 | Medium | `src/services/http.ts`, `session.tsx` | Each 401 renewed on its own, racing over a rotating refresh token. | Parallel requests after expiry: later renewals are refused and those requests fail. | **Fixed.** One renewal at a time (`singleFlight`), unit-tested. |
| 4 | Low | `src/auth/session.tsx` | Every 503 was blamed on `DASHBOARD_ORIGINS`. | A missing ZITADEL config sends the operator to the wrong setting. | **Fixed.** The server's own message is shown. |
| 5 | Medium | `src/auth/session.tsx` | The first load on `/auth/callback` could overwrite the callback's reload. | A freshly signed-in user is sent to sign-in again. | **Fixed.** Only the latest load sets the state. |
| 6 | Low | `src/services/mock/mock-data-source.ts` | The mock org audit hid registry rows about the organisation, which the API shows. | Sample and API mode differ. | **Fixed.** Test added. |
| 7 | Low | same | The mock accepted a duplicate disorder (the API answers 409). | The conflict path is never exercised in sample mode. | **Fixed.** Test added. |
| 8 | Low | same | The mock dropped a pseudonym sent for a doctor (the API answers 422). | A form bug shows only against the cloud. | **Fixed.** Test added. |
| 9 | Low | `src/auth/oidc.ts` | Its own fetch turned a network failure into a plain `Error`; a `.catch` was added on every call. | A separate message branch; a growing listener list. | **Fixed.** `ApiError(0)`, and the reset is attached once. |
| 10 | Low | `src/services/mock/sample-session.ts` | With storage blocked, sample sign-in did nothing. | Picking an account has no effect. | **Fixed.** The account is also kept in memory. |
