# Dashboard organisation admin screens (dashboard Phase 5)

- **Date:** 2026-10-26
- **Type:** code
- **Module:** M8 dashboard
- **Commits:** see `git log -- web/dashboard/` on `feat/dashboard`

## What changed
- **Dashboard:**
  - the organisation's name, kind and status;
  - counts of doctors, patients, wearables issued (and free to issue) and fixed gateways;
  - "needs attention": active patients without a doctor (no one sees their alerts) or without a wearable;
  - the latest changes.
- **Accounts:**
  - list doctors, patients and administrators, with names and e-mail from the directory (D14), filtered by role and status;
  - create a doctor or a patient; a patient needs a pseudonym, as `AccountIn` requires;
  - the **invite code is shown once** and held above the reloaded list, as on the system admin's organisation page;
  - disable a doctor or patient. The confirmation says what follows, from the current data:
    - for a doctor, which patients lose their doctor;
    - for a patient, whether a wearable is returned and monitoring ends.
  - Administrators have no Disable button, because the API disables doctors and patients only.
- **Patients:** search by pseudonym or name; filter by those without a doctor, those without a wearable, or disabled accounts.
- **A patient's page:**
  - assign or change the doctor (active doctors only; one at a time);
  - the wearable's status, path, gateway and when it was last heard from;
  - return the wearable (confirmation: monitoring ends, the device becomes free);
  - issue one of the active, granted, unissued wearables;
  - record and list disorders;
  - export, for a named destination: a summary, the record itself, and a JSON download. It says what an export leaves out (name, e-mail, ECG).
  - The patient's history comes from the audit log.
  - With a disabled account, the doctor and wearable forms are replaced by an explanation.
- **Devices:**
  - the devices granted to the organisation, read-only: status, path, gateway, last heard from, and the patient each is issued to (or "Free");
  - a quiet device is not called offline, because `stack.md` leaves presence across the two paths open.
- **Audit log:**
  - the organisation's changes, including the system administrator's grants and status changes;
  - patients by pseudonym with links, people by name, "You" for the signed-in admin, "System administrator" for registry actions;
  - doctor ids in details shown as names;
  - filtered by kind.
- **Names:**
  - `src/lib/people.ts` loads the directory for every screen;
  - if ZITADEL cannot be reached, the screens still work and show ids with a note, rather than failing the page.

## Why
Phase 5 of the dashboard rebuild: the organisation admin's screens over the D9 org-admin endpoints (`/accounts`, `/patients/*`, `/devices`, `/audit`, `/organisation`, `/directory`). The org admin sees no ECG, classifications or alerts.

## Evidence
`docs/testing/evidence/2026-10-26/dashboard-phase-5/`:
- `checks.txt`: typecheck, lint, 85 unit tests, production build. The new tests cover:
  - the disable wording;
  - pages still working when the directory fails;
  - sample data matching the API on returning and reissuing a wearable, an export logged with its destination, and refusing to disable an administrator.
- `e2e-mock.txt`: 38 browser tests, desktop and phone. The org admin flows:
  - create a patient, with the invite code gone after confirmation, then assign a doctor, issue a wearable, record a disorder, export with a download, and see each step in the history;
  - disabling a doctor names their patients, who then show as without a doctor;
  - administrators cannot be disabled;
  - returning a wearable frees it;
  - every organisation page fits a phone screen.
- `e2e-api.txt`: 8 browser tests against a real cloud stack. The new one:
  - names come from ZITADEL;
  - creates a patient and a doctor, then disables the doctor;
  - assigns a doctor, issues a wearable, records a disorder, exports, and checks the audit trail;
  - the new patient redeems their invite code in ZITADEL's login and lands in the patient area.

## Review
`/code-review high` found ten issues (`docs/testing/review-findings/2026-10-26-dashboard-phase-5-org-admin-screens.md`). Nine are fixed in a follow-up commit:
- a patient with no account is no longer treated as disabled;
- the export download is reliable, and stays available if a reload fails;
- nested audit details are readable;
- the create form remembers the last role;
- the audit formatter is shared, plus smaller cleanups.

One is accepted: the patient page loads the organisation-wide lists, for want of single-patient and patient-scoped audit endpoints.
