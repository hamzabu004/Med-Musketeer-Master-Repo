# Iteration 5 planned as ECG acquisition and live ECG; models and IDS/IPS move to Iteration 7

- **Date:** 2026-11-06
- **Type:** decision
- **Module:** M2 firmware | M5 gateway | M7 cloud | M8 dashboard | project
- **Commits:** e9256f8 (plan, doc updates, this entry); merged in b19959f (PR #18)

## What changed
- New plan `docs/iterations/iteration-5-ecg-on-demand.md`:
  - the wearable reads ECG from the AD8232, behind a front-end interface the ADS1292 will use;
  - a doctor starts and stops a live ECG from the dashboard, through the fixed path: new `command-v1`, `command-ack-v1` and `telemetry-v1` contracts, gateway bridging in both directions, cloud recording endpoints and a live strip;
  - 8 slices, test IDs TC-W05 to W07, TC-B13 to B16, TC-C36 to C41, TC-D15 to D17 and H-W04 to H-W07.
- Decisions confirmed by the owner:
  - ECG evaluation, the edge model, the gateway classifier, IDS/IPS and attack tests move to a parallel **Iteration 7**;
  - the wearable samples at **500 SPS**;
  - the sampler is **always on** (SDN high from boot);
  - the button alert stays **alert-payload-v1**, with its synthetic trace;
  - **patients may watch** their own recordings live.

  The remaining proposals are listed as open in the plan.
- `scope.md`'s timeline gains the new Iteration 5 and Iteration 7. References to the moved work now point to Iteration 7 in `gaps.md`, `cloud-backend.md` and the Iteration 2, 3 and 6 plans. `gaps.md` records the FYP-1 Final schedule risk.

## Why
The classifier is not ready, while ECG acquisition and on-demand ECG can be built and tested now with the AD8232. Real ECG reaches the dashboard through on-demand recordings, so the button alert can keep its synthetic trace unchanged. The ADS1292 supports 500 SPS natively, but not MIT-BIH's 360 Hz.

## Evidence
None (plan only).
