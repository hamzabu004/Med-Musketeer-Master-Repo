# Dashboard ported into the repo and stripped to a four-role skeleton (dashboard Phase 2)

- **Date:** 2026-10-25
- **Type:** code
- **Module:** M8 dashboard
- **Commits:** see `git log -- web/dashboard/` on `feat/dashboard`

## What changed
- **Imported:** the POC-Lite dashboard (`POC-Lite/starter/medmusketeer-poc`) is copied unchanged into `web/dashboard/` in its own commit, so every later change is a diff against it.
- **Renamed:** package `medmusketeer-dashboard`; browser storage keys `medmusketeer:dashboard:*`; "POC", "demo" and "simulated" wording removed.
- **Removed (no basis in the system):**
  - heart rate (trend chart, readings, settings);
  - editable monitoring stations and doctor/device-to-station assignment;
  - the identities page, the org-admin device wizard, org-admin IDS/IPS pages, system configuration, org-wide settings;
  - demo login, `DemoSession`, demo state and reset, and the mock services and seed data;
  - the fake "live" ECG animation.
- **Removed for rewriting (restored from the import commit when their screens are built):** the old domain types and the components built on them (alert and patient tables, monitoring cards, ECG request panel, event charts). Phase 3 rewrites the types and data layer from the cloud API; Phases 4–6 adapt these components to it.
- **Kept:** the design system (tokens, IBM Plex Sans, `ui/*`), the app shell and sidebar, the role guard and the ECG waveform.
- **New skeleton:**
  - the four cloud roles (`src/auth/roles.ts`), each with its own area (`/system`, `/org`, `/doctor`, `/patient`) and sidebar;
  - placeholder pages for every planned screen, saying what each will show;
  - a session placeholder (nobody is signed in until Phase 3, so every area redirects to sign-in).
- **Tooling:**
  - Vitest + Testing Library;
  - Playwright on desktop and phone;
  - `npm run gen:api` (openapi-typescript), with the generated `src/api/schema.d.ts` committed.
- **Security:** Next.js 16.3.4 → 16.4.3, which fixes a critical advisory (GHSA-673q-mjm6-r5xr, unauthenticated RCE in `use cache` functions) and two others; the transitive sharp and zod advisories are fixed too. `npm audit` reports 0.

## Why
Phase 2 of the dashboard rebuild: the POC modelled a system that no longer exists (three roles, heart rate, editable stations). It now starts from what the cloud defines.

## Evidence
`docs/testing/evidence/2026-10-25/dashboard/`:
- `checks.txt`: typecheck, lint, 8 unit tests and the production build;
- `e2e.txt`: 12 Playwright tests, desktop and phone (sign-in page, signed-out redirects for all four areas, no horizontal scroll).

The navigation test fails if a sidebar link points to a page that does not exist or lies outside its role's area.

## Review
`/code-review high` found ten issues (`docs/testing/review-findings/2026-10-26-dashboard-phase-2-port-and-strip.md`). Seven are fixed in a follow-up commit:
- a cross-platform `gen:api`;
- a dedicated e2e port, with no server reuse;
- `patientId` in the session;
- the doctor's segment viewer moved under the patient, with one shared path helper;
- ESM config files;
- `next-env.d.ts` untracked;
- one `RoleArea` layout.

The ECG scale, the signed-in redirect from `/login` and the unused kit wait for the phases that rewrite them.
