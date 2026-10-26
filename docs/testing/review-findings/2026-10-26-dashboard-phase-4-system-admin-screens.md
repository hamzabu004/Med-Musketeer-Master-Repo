# Code review findings — dashboard Phase 4 (system admin screens)

- **Reviewed:** commit `73a32b9` on `feat/dashboard`, `/code-review high`, 2026-10-26
- **Status:** 9 fixed, 1 accepted.
- **Verified:** typecheck, lint, 79 unit tests, build, 30 sample-mode and 7 API-mode browser tests pass after the fixes (`docs/testing/evidence/2026-10-26/dashboard-phase-4/`).

| # | Severity | File | Finding | Failure scenario | Outcome |
|---|---|---|---|---|---|
| 1 | High | `src/features/system/organisation-detail.tsx` | The one-time invite code lived inside the reloaded part of the page. | The reload after creating an admin fails, so the error state unmounts the code. The API cannot return it again. | **Fixed.** The code is held above the reloaded part and stays until the admin confirms. |
| 2 | High | `src/components/ui/one-time-code.tsx` | "Copied" was shown even when nothing was copied. | Over plain http there is no clipboard: the admin trusts "Copied" and loses the code. | **Fixed.** "Copied" only on success; otherwise "write the code down". |
| 3 | Medium | `src/features/system/attack-tests.tsx` | Windows older than the newest 1000 events were marked "missed detection". | A false negative in the detection metrics. | **Fixed.** Such windows show "Not covered", unit-tested. |
| 4 | Low | `src/features/system/organisation-detail.tsx` | Admins older than the newest 1000 registry changes vanished from the list. | "No administrator recorded" for an organisation that has one. | **Fixed (disclosed).** The page says when the search window is full. A real fix needs an endpoint listing an organisation's admins. |
| 5 | Low | `src/features/system/attack-tests.tsx` | An empty rate sent `rate_pps: 0`. | A zero-rate test, then a false "missed detection". | **Fixed.** Required, at least 1. |
| 6 | Low | `src/features/system/system-dashboard.tsx` | "Loaded" showed the render time, not the fetch time. | Stale data looked fresh. | **Fixed.** `useResource` records `fetchedAt`. |
| 7 | Low | `src/features/system/organisation-detail.tsx` | One grants request per registered device on each load. | Slow with hundreds of devices. | **Accepted.** No grants-by-organisation endpoint exists. Recorded as a cloud gap for when the registry grows. |
| 8 | Low | `devices.tsx`, `security-events.tsx` | `useMemo` depended on a new object every render. | Wasted work on every keystroke. | **Fixed.** Depends on the data. |
| 9 | Low | several | `reload` existed only when ready, so a change made while the list showed an error did not refresh it. | A stale list after a successful registration. | **Fixed.** `reload` exists in every state; the guards are gone. |
| 10 | Low | `form.tsx`, `device-detail.tsx`, `attack-tests.tsx` | The unused `LabeledSelect` duplicated `Select`; `shortId` and a label were re-implemented. | Drift between copies. | **Fixed.** Removed and reused. |
