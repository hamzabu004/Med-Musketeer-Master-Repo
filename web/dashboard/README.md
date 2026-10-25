# MedMusketeer POC Starter

Concrete starter skeleton for the MedMusketeer proof-of-concept dashboard.

## Stack

- Next.js 16.3
- React 19.2
- TypeScript
- Tailwind CSS 4
- Recharts
- Lucide React

## Run

```bash
npm install
npm run dev
```

## Demo credentials

```text
patient@medmusketeer.demo
doctor@medmusketeer.demo
admin@medmusketeer.demo

Password: demo123
```

## Design

The starter uses centralized tokens in `src/app/globals.css` and `src/config/theme.ts`.

The initial visual system is light-only, deep navy + cyan, IBM Plex Sans, sharp 4–6 px corners, flat bordered surfaces, a collapsible sidebar, and a clinical monitoring-console aesthetic.

Do not hardcode design colors into individual components.

## Validate

```bash
npm run typecheck
npm run lint
npm run build
```
