# Code review findings — dashboard Phase 2 (POC ported and stripped to a four-role skeleton)

- **Reviewed:** commit `cd5cf1b` on `feat/dashboard`, `/code-review high`, 2026-10-26 (the import commit `3c5847c` is the POC unchanged and was not reviewed)
- **Status:** 7 fixed, 3 deferred to the phase that rewrites the code.
- **Verified:** typecheck, lint, 8 unit tests, build and 12 Playwright tests pass after the fixes (`docs/testing/evidence/2026-10-25/dashboard/`).

| # | Severity | File | Finding | Failure scenario | Outcome |
|---|---|---|---|---|---|
| 1 | Medium | `src/components/charts/ecg-waveform.tsx` | The waveform still scales by a fixed `stableAmplitude = 20`, made for the removed simulated signal; one sample draws nothing. | Real ECG (mV or ADC counts) draws flat or clipped. | **Deferred to Phase 6**, which rewrites the waveform for int16 samples at `fs_hz` with a mm/mV grid. No screen uses it yet. |
| 2 | Medium | `src/app/login/page.tsx` | A signed-in user who opens `/login` is not sent to their dashboard (the deleted login form did this). | Once sign-in works, a bookmark to `/login` strands the user. | **Deferred to Phase 3**, which rewrites the sign-in page. |
| 3 | Low | `package.json` | `gen:api` used POSIX `${VAR:-default}`, which cmd.exe does not expand. | Type generation fails on Windows. | **Fixed.** `scripts/gen-api.mjs` (plain Node). |
| 4 | Low | `playwright.config.mts` | The port came from the generic `PORT`, and an existing server was reused outside CI. | Tests run against `next dev` or a stale build on that port. | **Fixed.** `DASHBOARD_E2E_PORT` (default 3100), never reuse a server. |
| 5 | Low | `src/auth/session.ts` | `Session` claimed to mirror `/me` but lacked `patient_id`. | Patient screens would need a second lookup. | **Fixed.** `patientId` added. |
| 6 | Low | `src/components/app-shell/sidebar.tsx` | `/doctor/segments/[id]` sat under no sidebar item; the prefix check was written twice. | No item is highlighted on the segment viewer. | **Fixed.** The viewer moved to `/doctor/patients/[patientId]/segments/[segmentId]`; one `isWithin` helper, unit-tested. |
| 7 | Low | `vitest.config.ts` | ESM syntax in a CommonJS package; Vite warns it will break. | The config stops loading in a future Vite. | **Fixed.** `vitest.config.mts` and `playwright.config.mts`. |
| 8 | Low | several | Components, `recharts` and Testing Library are unused in the skeleton. | Dead code paid for by lint, typecheck and installs. | **Deferred.** They are the kept design system and the planned tooling, used from Phase 3 on. |
| 9 | Low | `next-env.d.ts` | The generated file was committed and flips between dev and build. | A dirty tree after every dev/build switch. | **Fixed.** Ignored and untracked; `typecheck` runs `next typegen` first. |
| 10 | Low | `src/components/auth/role-guard.tsx`, area layouts | The route check in the guard was redundant, and the four layouts were copies. | A shell change had to be made four times. | **Fixed.** The guard checks the role only; one `RoleArea` component. |
