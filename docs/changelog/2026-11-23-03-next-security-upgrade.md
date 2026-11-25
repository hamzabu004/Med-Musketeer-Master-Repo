# Next.js 16.4.6, a security release

- **Date:** 2026-11-23
- **Type:** code
- **Module:** M8 dashboard
- **Commits:** pending

## What changed
- `next` 16.4.3 → 16.4.6, and `eslint-config-next` along with it. Both stay pinned to exact versions. Only these two packages and their lock entries changed.
- `npm audit --omit=dev` (the packages the deployed dashboard ships): 0 vulnerabilities, down from one moderate advisory on `next`.
- The full `npm audit` still lists one moderate advisory, in `minimatch`, which `typescript-eslint` uses. It comes from the development lint tooling, which is not part of the deployed dashboard, and it was there before this change. It is left for the lint tooling's own update.

## Why
Next.js 16.0.0 to 16.4.4 is affected by seven advisories. Among them are a cross-client response injection in self-hosted applications (GHSA-pc58-hwjq-p385), an HttpOnly cookie exposure on Edge routes (GHSA-f3mh-rxg3-f5g2), an SVG rejection bypass in image optimisation (GHSA-7qx7-33qx-rqx2), and several `use cache` disclosure and poisoning issues. The dashboard is public at medmusketeer.site. `next build` on 16.4.3 had also started stopping every other run with a "known security vulnerability" warning, which broke the dashboard's browser test runs.

## Evidence
Run locally on this branch, not stored:
- `npm run lint`, `npm run typecheck`: clean.
- `vitest`: 112 passed.
- `next build`: succeeds, with no security stop.
- Sample-mode Playwright: 54 passed, desktop and phone.
- API-mode Playwright through `scripts/api-e2e.sh`, against the real cloud stack: 9 passed.
- The production image, `web/dashboard/Dockerfile` built with podman, builds and reports Next.js 16.4.6.
