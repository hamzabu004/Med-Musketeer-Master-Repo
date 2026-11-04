# Public deployment overlay with Let's Encrypt

- **Date:** 2026-10-30 (deployed 2026-11-04)
- **Type:** code
- **Module:** M7 cloud
- **Commits:** pending

## What changed
- `cloud/compose.public.yaml`, layered on `compose.yaml`: HTTPS on 443 with Let's Encrypt (HTTP-01 on 80), HTTP redirected to HTTPS, ZITADEL set to HTTPS, and the dashboard started by default.
- `cloud/traefik/public.yml`: one host name each for the dashboard, API and ZITADEL, a per-client rate limit and security headers. The API's `/internal`, `/docs`, `/redoc` and `/openapi.json` are not routed.
- The cloud will run on an Oracle Cloud VM, with public access for the dashboard, API and MQTT. The dashboard keeps its own host name and CORS (D14's open question).

## Why
The dashboard signs in with PKCE, which needs `crypto.subtle`, so browsers allow it only on HTTPS or localhost. The user wants the dashboard, API and MQTT public on a domain rather than limited to a tailnet.

## Evidence
A throwaway local stack with fake host names: all services healthy; dashboard, API and ZITADEL routes answer; blocked paths and unknown hosts answer 404; HTTP redirects to HTTPS; CORS allows the dashboard's origin; the rate limit answers 429 under load. Deployed on 2026-11-04 to the Oracle VM at `medmusketeer.site`:
- Let's Encrypt production certificates for `app`, `api` and `auth` verify.
- From outside, only 22, 80, 443 and 8883 answer, and HTTP redirects to HTTPS.
- `/internal` and `/docs` answer 404.
- A headless browser signed in as the system admin through ZITADEL with PKCE. It landed on `/system/dashboard`, `/me` answered 200, and the token was in sessionStorage only.
- The stack came back healthy after a reboot.

The ACME e-mail is optional, because Let's Encrypt no longer sends expiry e-mails. Let's Encrypt's staging server was unreachable from the VM (connection reset), so production was used once port 80 was confirmed reachable.
