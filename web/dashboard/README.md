# MedMusketeer Dashboard

The web dashboard for MedMusketeer (module M8). It is rebuilt from the POC-Lite proof of concept on top of the cloud API (`cloud/`), and serves four roles: system admin, organisation admin, doctor and patient. The API enforces what each role may do (D9 in `docs/decisions/cloud-backend.md`); the dashboard shows each role its own area.

**Status:** being rebuilt. The routes exist as placeholders, and sign-in and data are not connected yet. See the plan phases in `docs/changelog/` (dashboard entries).

## Stack

- Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4
- Recharts, Lucide React
- Vitest + Testing Library (unit), Playwright (browser)
- `openapi-typescript` (API types from the cloud's OpenAPI document)

## Run

```bash
npm install
npm run dev        # http://localhost:3000
```

## Validate

```bash
npm run typecheck
npm run lint
npm test           # unit tests (Vitest)
npm run build
npx playwright install chromium   # once
npm run test:e2e   # browser tests, desktop and phone (builds and starts the app on port 3100)
```

## API types

`src/api/schema.d.ts` is generated from the cloud API's OpenAPI document and committed. Regenerate it when the API changes:

```bash
npm run gen:api                                   # from a running API at http://localhost:8000
OPENAPI_SOURCE=path/to/openapi.json npm run gen:api
```

## Layout

| Path | What |
|---|---|
| `src/app/{system,org,doctor,patient}/` | One area per role, each behind `RoleGuard` |
| `src/auth/` | Roles and the session |
| `src/config/navigation.ts` | The sidebar of each role |
| `src/components/ui/`, `app-shell/` | Design system and shell, kept from the POC |
| `src/api/schema.d.ts` | Generated API types |

## Design

Centralised tokens in `src/app/globals.css` and `src/config/theme.ts`: light-only, deep navy and cyan, IBM Plex Sans, 4–6 px corners, flat bordered surfaces, a collapsible sidebar. Do not hardcode colours in components.
