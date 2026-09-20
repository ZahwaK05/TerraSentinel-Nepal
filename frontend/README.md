# TerraSentinel-Nepal — frontend

Next.js 16 / React 19 / TypeScript dashboard for the cascading flood/GLOF risk
platform. Dark "command center" design: risk color (green/amber/orange/red) is
the only saturated color on the page, everything else is neutral, so severity
is what actually catches your eye.

Verified working in this environment: `npm install` → zero vulnerabilities,
`next build` → compiles clean with TypeScript strict mode, `next start` →
serves and renders correctly.

## Run it

```bash
npm install
npm run dev
```

Open http://localhost:3000. Runs immediately on mock data — no backend
required to see or demo it.

## What's in it

- **Historical replay slider** (Jun 11–15, 2021 Melamchi flood dates) with
  auto-play — drag it or hit play and watch risk scores climb, zone colors
  shift, and the debris corridor light up on the map. This is the "judges
  watch the disaster develop" demo moment from the original brief.
- **Schematic river map** — 4 zones along a drawn river, colored live by risk
  level, clickable and keyboard-navigable.
- **Zone detail panel** — population, roads, bridges, schools, power assets,
  hazard corridor description, and an action list that only appears once risk
  crosses HIGH/CRITICAL.
- **6-card dashboard strip** — risk score, population exposed, infrastructure
  count, rainfall, lake change, displacement.
- **Alert banner** — appears automatically when any zone crosses HIGH/
  CRITICAL, with a "Play voice alert" button using the browser's built-in
  speech synthesis (a stand-in for Amazon Polly, since a static site can't
  call AWS directly from the browser without your API in front of it).
- **Rescue priority module** — the post-disaster thermal/acoustic/RF fusion
  cards, each with a working "Deploy rescue team" button.
- **Basin-wide risk grid** — a real Leaflet heatmap over OpenStreetMap tiles,
  fed by the actual geospatial/ML team's per-cell output (32,000+ real grid
  cells across the Melamchi basin, not mock data). Toggle between the 2021
  and 2026 datasets. Works in local dev with zero backend - it reads the
  converted GeoJSON straight from `public/data/`, and automatically switches
  to fetching from the real API once `NEXT_PUBLIC_API_URL` is set.

## Project structure

```
app/
  layout.tsx       Root layout, loads IBM Plex fonts
  globals.css       All design tokens + component styles (no CSS framework)
  page.tsx          Top-level state (day, selected zone, toast) + layout
components/
  Header.tsx         Brand, live clock, system status pill
  AlertBanner.tsx     HIGH/CRITICAL banner + voice alert
  TimeBar.tsx         Day slider + play/pause
  ZoneList.tsx        Left-rail zone list
  MapPanel.tsx         Schematic SVG river map
  DetailPanel.tsx      Right-rail zone detail + government actions
  CardsStrip.tsx       6-card summary strip
  RescueGrid.tsx       Rescue priority cards
  Toast.tsx            Bottom toast notification
lib/
  types.ts            Shared TS types
  risk.ts              Risk-level thresholds/colors (kept in sync with the
                        backend's risk_level_from_score())
  mockData.ts           Mock zones + rescue cases, matching the team's
                          agreed JSON contracts
  api.ts                Fetch wrapper for the real API - unused by default
public/data/
  melamchi_2021_risk_points.geojson   Real converted grid (2021, historical)
  melamchi_2026_risk_points.geojson   Real converted grid (2026, current)
```

## The basin-wide risk grid is real data, not mock

Unlike the 4-zone dashboard (which is still illustrative mock data), the
heatmap panel reads Zahwa's actual geospatial/ML output - converted from
her CSV deliverable with `scripts/convert_risk_grid.py` in the backend repo.
32,435 real grid cells across the Melamchi basin, each with an actual
computed risk score. It works today, with no backend deployed, because the
converted files are checked into `public/data/`. Once `NEXT_PUBLIC_API_URL`
is set, `lib/api.ts`'s `fetchRiskGrid()` automatically switches to calling
`GET /risk-map/{year}` on the real API instead.

## Connecting to the real backend

Right now every number on the page comes from `lib/mockData.ts`. Once
Manas's AWS backend is deployed and you have the `ApiUrl` output:

1. Copy `.env.local.example` to `.env.local` and paste in the URL.
2. In `app/page.tsx`, swap the `ZONES` / `RESCUE_CASES` imports from
   `lib/mockData` for calls to the functions in `lib/api.ts`
   (`fetchRiskEvents()`, `fetchInfrastructure()`, `fetchAlerts()`).
3. Nothing else changes — every component already takes zones/cases as
   props, so swapping the data source doesn't touch the UI code.

`lib/api.ts` already has typed fetch functions for every route in the
backend's spec (`GET /risk`, `/risk/{zone}`, `/infrastructure`, `/alerts`,
and `POST /simulate-event`) ready to wire in.

## Deploy

Any static/Node host works (Vercel is the zero-config default for Next.js):

```bash
npm run build
npm start
```

Or connect the repo to Vercel/Netlify and it builds automatically on push.

## Honesty note

All data shown is mock data seeded for the demo, clearly labeled in the
page's footer. Risk index is described throughout as a relative score, not a
calibrated probability, matching Member 1's spec.
