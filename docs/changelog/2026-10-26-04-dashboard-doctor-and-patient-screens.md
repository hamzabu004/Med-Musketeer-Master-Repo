# Dashboard doctor and patient screens (dashboard Phase 6)

- **Date:** 2026-10-26
- **Type:** code
- **Module:** M8 dashboard
- **Commits:** see `git log -- web/dashboard/` on `feat/dashboard`

## What changed
- **ECG strip** (`src/components/charts/ecg-waveform.tsx`, rewritten from the POC's):
  - draws the samples decoded from the API's int16le-base64 chunks at the segment's `fs_hz`, on a clinical grid at 25 mm/s and 10 mm/mV (1 mm and 5 mm squares) with a time axis in seconds;
  - the strip keeps paper proportions and scrolls inside its own box on narrow screens;
  - pointing at it reads time and voltage.
  - The gain is assumed to be 200 counts/mV (MIT-BIH, as seed-dev and the sample data use), and the strip says so, because segments do not carry the wearable's gain.
- **Doctor:**
  - **Dashboard:** unacknowledged alerts (with acknowledge), the patient count, wearables heard from in the last 15 minutes, and the open classifications.
  - **Alerts:** across the doctor's patients; unacknowledged or all, by severity; acknowledge; "N new since you opened this page".
  - **Alert detail:**
    - classification, confidence, severity, where it was classified (gateway on the fixed path, cloud on the mobile path), the wearable;
    - the alert's ECG segment with every classification;
    - acknowledge. A 409 (acknowledged elsewhere) reloads, to show who acknowledged it.
  - **Patients:** the doctor's own, with unacknowledged counts and the wearable's path and last contact.
  - **A patient's page:**
    - the wearable's status, path and gateway, and when it was last heard from, with no online/offline verdict (`stack.md` liveness);
    - known disorders, alerts, and ECG segments;
    - on-demand recording.
  - **Segment viewer:** an alert segment or a recording, with its classifications.
- **Patient:**
  - **Dashboard:** organisation, their doctor's name (directory), latest alerts, and the "research prototype, not a medical device, not medical advice" notice;
  - **Alerts:** read-only, showing who acknowledged each one; each opens its ECG;
  - **ECG Recordings:** their segments, and the viewer.
- **Polling:** alert screens re-read every 15 s while visible, and when the page becomes visible again. This stands in for the alert push (capability `alertStream`) until the cloud has it.
- **Latency checkpoint:** a `performance.mark("mm:dashboard-render", { detail: { alert_id, created_at } })` the first time each alert is drawn on a page load. This is the "dashboard render" hop of the methodology in `stack.md`; it is captured for measurement only.
- **On-demand recording** (capability `ecgRequests`):
  - **API mode:** shows as not available yet, since how a recording starts and stops is open (`gaps.md`).
  - **Contract:** `recordings.list/request`, provisional, shaped on the `commands` table (`sent | acked | expired`) and the `recording` segment that references the command.
  - **Sample mode:**
    - a wearable heard from in the last 15 minutes acks after 3 s and streams for the requested 10–60 s, then the recording segment appears; a quiet wearable's command expires after 60 s;
    - one recording at a time per patient;
    - refused for a patient without a wearable.
  - The sample world has one finished 30 s recording.
- **Removed:** the placeholder screen component. No screen is a placeholder any more.
- **Browser test helper:** `signIn` handles ZITADEL's "Accounts" chooser, which appears after a sign-out in the same browser.

## Why
Phase 6 of the dashboard rebuild: the doctor's and patient's screens over the care endpoints (`/alerts`, `/patients/{id}/alerts`, `/alerts/{id}/acknowledge`, `/patients/{id}/segments`, `/segments/{id}`, `/directory`). Doctors see only their current patients and patients only themselves (D9); only a doctor acknowledges.

## Evidence
`docs/testing/evidence/2026-10-26/dashboard-phase-6/`:
- `checks.txt`: typecheck, lint, 94 unit tests, production build. The new tests cover:
  - strip geometry at paper speed and gain;
  - recording states;
  - the render checkpoint marking each alert once;
  - classification labels;
  - sample recordings (ack, record, segment served, one at a time, refusals).
- `e2e-mock.txt`: 48 browser tests, desktop and phone.
  - **Doctor:**
    - opens an alert's ECG (10 s at 360 Hz, two classifications), acknowledges it, and it leaves the inbox;
    - one render mark per alert;
    - requests a 10 s recording and views it once recorded;
    - only their own patients (another doctor's patient reads "not found");
    - every page fits a phone.
  - **Patient:** their doctor's name, their own alerts without Acknowledge, and their ECG including the recording.
- `e2e-api.txt`: 9 browser tests against a real cloud stack. The new one:
  - the doctor's dashboard draws 3 unacknowledged alerts, with 3 render marks;
  - the alert's ECG is decoded from the API's chunks;
  - the acknowledgement survives a reload;
  - the patient page shows the fixed path and "on-demand recording is not available yet";
  - the patient then sees their doctor's name and the three acknowledged alerts, without an Acknowledge button.
