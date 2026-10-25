# MedMusketeer Dashboard

The web dashboard for MedMusketeer (module M8). It is rebuilt from the POC-Lite proof of concept on top of the cloud API (`cloud/`), and serves four roles: system admin, organisation admin, doctor and patient. The API enforces what each role may do (D9 in `docs/decisions/cloud-backend.md`); the dashboard shows each role its own area.

**Status:** being rebuilt. Sign-in, the data layer and the system admin screens work in both modes; the org admin, doctor and patient screens are still placeholders. See the dashboard entries in `docs/changelog/`.

## Stack

- Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4
- Recharts, Lucide React
- Vitest + Testing Library (unit), Playwright (browser)
- `openapi-typescript` (API types from the cloud's OpenAPI document)

## Run

```bash
npm install
cp .env.example .env.local   # then pick the mode
npm run dev                  # http://localhost:3000
```

Two data sources, chosen at build time with `NEXT_PUBLIC_DATA_SOURCE`:

| Mode | What it needs | Sign-in |
|---|---|---|
| `api` (default) | The cloud stack (`cloud/`) at `NEXT_PUBLIC_API_URL`, whose `DASHBOARD_ORIGINS` lists this dashboard's origin. Seed it with `docker compose exec api python -m app.manage seed-dev` | ZITADEL (authorization code + PKCE), settings from the API's `/auth/config` |
| `mock` | Nothing: sample data in the browser, with the same D9 rules as the API | Pick a sample account |

The two are never mixed. In API mode, a feature the cloud does not serve yet (on-demand ECG, attack tests, alert push) shows as unavailable (`src/config/capabilities.ts`). In sample mode the header shows "Sample data".

## Validate

```bash
npm run typecheck
npm run lint
npm test           # unit tests (Vitest)
npm run build
npx playwright install chromium   # once
npm run test:e2e   # browser tests in sample mode, desktop and phone (port DASHBOARD_E2E_PORT, default 3100)
scripts/api-e2e.sh # browser tests in API mode: brings up its own cloud stack, seeds it, signs in each role through ZITADEL, removes the stack
```

## API types

`src/api/openapi.json` (the cloud API's OpenAPI document) and `src/api/schema.d.ts` (types generated from it) are committed. A unit test checks that every call the dashboard makes is a path and method in that document. Regenerate both when the API changes:

```bash
npm run gen:api                                   # from a running API at http://localhost:8000
OPENAPI_SOURCE=path/to/openapi.json npm run gen:api   # or from a file (scripts/gen-api.mjs)
```

## Layout

| Path | What |
|---|---|
| `src/app/{system,org,doctor,patient}/` | One area per role, each laid out by `RoleArea` (guard + shell) |
| `src/auth/` | Roles, the session (`useSession`, `useData`) and ZITADEL sign-in |
| `src/api/` | API types (aliases of the generated schema) and error mapping |
| `src/services/` | The data-source contract, the API implementation and the sample-data implementation (`mock/`) |
| `src/lib/ecg.ts` | Decoding the API's int16le-base64 ECG chunks |
| `src/config/navigation.ts` | The sidebar of each role |
| `src/components/ui/`, `app-shell/` | Design system and shell, kept from the POC |
| `src/api/schema.d.ts` | Generated API types |

## Design

Centralised tokens in `src/app/globals.css` and `src/config/theme.ts`: light-only, deep navy and cyan, IBM Plex Sans, 4–6 px corners, flat bordered surfaces, a collapsible sidebar. Do not hardcode colours in components.
