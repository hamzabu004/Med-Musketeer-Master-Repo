# Dashboard documentation (dashboard Phase 7)

- **Date:** 2026-10-26
- **Type:** docs
- **Module:** M8 dashboard
- **Commits:** see `git log -- docs/ web/dashboard/README.md` on `feat/dashboard`

## What changed
- **`docs/iterations/iteration-6-dashboard.md`** (new), the screen-level spec of the dashboard:
  - the two data modes;
  - every screen of the four roles, with its actions and endpoints;
  - the display rules: ECG strip, liveness, names, errors, invite codes, alert refresh, the latency checkpoint, tokens;
  - what waits for the cloud, with how the dashboard works around it meanwhile;
  - deployment on the cloud Pi;
  - the tests.
- **`docs/testing/test_traceability.md`:** dashboard cases TC-D01 to TC-D12, each mapped to its unit and browser tests and the evidence.
- **`docs/decisions/gaps.md`:**
  - the missing screen-level spec is resolved;
  - the invite-code redemption gap is resolved (TC-D05);
  - added: deployment on the cloud Pi and the same-origin question, the cloud endpoints the dashboard works around, the unstored ECG gain, and ZITADEL self-registration.
- **`docs/decisions/scope.md` and `stack.md`:** the new dashboard replaces the POC and will be served from the cloud Pi, not Vercel.
- **`docs/decisions/cloud-backend.md`:**
  - D14's reason for rejecting a same-origin proxy (the dashboard was to be on Vercel) is marked for revisiting with the Pi deployment;
  - D12's onboarding note points to the dashboard's redemption tests.
- **`web/dashboard/README.md`:** a deployment section, and the features in the layout table.

## Why
Phase 7 of the dashboard rebuild. Vercel deployment was dropped: the dashboard will be deployed on the cloud Pi, so its deployment belongs with the cloud's (Iteration 3, Slice 6) and its public domain.
