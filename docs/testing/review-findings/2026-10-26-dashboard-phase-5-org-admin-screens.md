# Review findings: dashboard Phase 5, organisation admin screens

- **Commit reviewed:** `f0906cf` (`/code-review high`)
- **Date:** 2026-10-26
- **Outcome:** 9 fixed, 1 accepted

| # | Finding | Outcome |
|---|---|---|
| 1 | A patient with no account (`patients.user_id` null; the integration world seeds `P-spare`) was treated as disabled: the patient page hid the doctor and wearable forms, though `require_active_account` allows both. | **Fixed.** Only `account_status === "disabled"` blocks; the status reads "No account". A sample-data test assigns a doctor and issues a wearable to such a patient. |
| 2 | The same patient was counted as disabled on the dashboard, left out of both "needs attention" lists, and listed under the "Disabled accounts" filter. | **Fixed** with #1 on the dashboard and patients list. |
| 3 | Download JSON clicked an anchor outside the document and revoked the blob URL on the next tick, which can break the download in some browsers; a lost export costs a new export row. | **Fixed.** The anchor is added to the document for the click, and the URL is revoked after 60 s. |
| 4 | The org audit table printed nested detail values as `[object Object]`. | **Fixed** with #8. A unit test covers nested values. |
| 5 | The finished export was held above `<Loaded>` but shown inside it, so a failed reload hid the Download button. | **Fixed.** While the page cannot load, the export is shown on its own above the error. |
| 6 | The patient page loads every patient, device and account, and 1000 audit rows, and reloads them all after each change. | **Accepted.** There is no patient-scoped audit endpoint or single-patient read for the org admin, and the cost is small at the organisation sizes of this project. A cloud gap, recorded with Phase 4's: `GET /patients/{id}` and a patient-scoped audit filter. The 1000-row cut-off is already disclosed on the page. |
| 7 | The create-account form reset to "Doctor" after each invite code, since the form unmounts while the code is shown. | **Fixed.** The role is held in the Accounts screen. |
| 8 | The audit details formatter was copied between the registry and organisation tables, and the copies had drifted. | **Fixed.** Both use `formatAuditDetails` in `src/lib/audit.ts`. |
| 9 | Ids shortened by hand (`slice(0, 8)`) rather than with `shortId()`. | **Fixed.** |
| 10 | A dead `resource.status === "ready"` check inside `<Loaded>` to reach `fetchedAt`. | **Fixed.** `<Loaded>` passes `{ fetchedAt }` to its children; also used on the system dashboard. |

## Verification
- typecheck, lint, 88 unit tests, build;
- 38 sample-mode browser tests;
- 8 API-mode browser tests against a fresh cloud stack.
