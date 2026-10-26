# Review findings: dashboard Phase 6, doctor and patient screens

- **Commit reviewed:** `02bbfc5` (`/code-review high`)
- **Date:** 2026-10-26
- **Outcome:** 9 fixed, 1 mitigated (needs a cloud endpoint)

| # | Finding | Outcome |
|---|---|---|
| 1 | The alert detail page searched only the doctor's newest 1000 alerts, so an older alert still in the Unacknowledged inbox read "not found". | **Mitigated.** It now searches the newest 1000 unacknowledged and the newest 1000 of all alerts, which are the two lists the inbox links from. An alert older than both, reached by a saved link, still reads "not found". The fix is a cloud gap: `GET /alerts/{alert_id}`. |
| 2 | In sample mode, on-demand recordings expired once the session was over 15 minutes old, because sample `last_seen` is fixed when the world is created. | **Fixed.** A sample wearable that has ever reported acks. The unit test now runs an hour into the session. |
| 3 | The dashboard-render mark was taken for alerts drawn on opening, or long after a filter hid them, which would skew latency figures. | **Fixed.** Each mark carries `backlog: true` for an alert created before the page loaded, so analysis can leave it out. The code documents that a latency run uses an unfiltered list, since the mark is taken at render. |
| 4 | An unexpected severity (free text in the schema) was shown in the calm "info" tone, and "critical" was hidden by the High filter. | **Fixed.** Only "low" is calm; "critical" counts as high; any other value shows as needing attention. Unit-tested. |
| 5 | Acknowledge became clickable again between the API's answer and the reload, so a double click got a 409 instead of the success notice. | **Fixed.** An alert stays pending ("Acknowledging…", disabled) from the click until the reloaded list shows it acknowledged. A 409 keeps it pending; another refusal releases it to try again. |
| 6 | Counts from capped lists were silently wrong: the dashboard stopped at 1000, and the patient page counted unacknowledged alerts only among the newest 200. | **Fixed.** Full lists read "1000+". The patient page counts from a separate unacknowledged query, and says when its lists show only the newest 200. |
| 7 | While the recordings list was loading or had failed, Request was enabled, and the failure was not shown. | **Fixed.** Request waits until the list is read; a failure is shown with Try again. |
| 8 | Each 15 s poll reloaded patients, devices and the directory (ZITADEL lookups) as well as the alerts. | **Fixed.** Patients, devices and names load once per page. Only alerts (and a patient's segments) are polled, and the patient screens do the same. |
| 9 | `touch-action: pan-x` on the ECG strip stopped vertical page scrolling on phones. | **Fixed.** Removed. |
| 10 | The last second label ("10 s") was drawn outside the strip and clipped. | **Fixed.** Only labels that fit inside the strip are drawn. |

## Verification
- typecheck, lint, 96 unit tests, build;
- 48 sample-mode browser tests;
- 9 API-mode browser tests against a fresh cloud stack.
