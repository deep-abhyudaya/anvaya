# 03 — Frontend: Next.js 15

## What is Next.js?

Next.js is a React framework that handles routing, server-side rendering, and build tooling for you. ANVAYA uses **Next.js 15** with the **App Router** (the newer folder-based routing system).

## App Router and file-based routing

In the App Router, every folder inside `frontend/app/` becomes a URL. A `page.tsx` file in that folder is the page content.

For example:

| File | URL |
|---|---|
| `frontend/app/page.tsx` | `/` |
| `frontend/app/overview/page.tsx` | `/overview` |
| `frontend/app/incidents/page.tsx` | `/incidents` |
| `frontend/app/impact-gallery/page.tsx` | `/impact-gallery` |

This is called **file-system-based routing**. You do not need to write a route table manually; Next.js scans the folders and creates the routes for you.

## Dynamic routes

A folder with square brackets creates a **dynamic route**. For example `frontend/app/incidents/[id]/page.tsx` would match `/incidents/abc123` and give you the `id` parameter. ANVAYA currently sends users to the shared `/incidents` page and keeps the selected incident in client state, so it does not use dynamic segment pages. Instead it uses query parameters and the global Zustand-style store. The backend does use dynamic routes such as `/api/v1/incidents/{incident_id}`.

## The pages and what they show

| Page | Purpose |
|---|---|
| `/` (Arbor) | Landing / entry page |
| `/overview` | Live SOC posture, active incidents, sealed count, ecosystem health |
| `/incidents` | Incident list and detail view |
| `/impact-gallery` | Cards showing blast-radius impact for incidents |
| `/reach-board` | Asset reachability matrix |
| `/miss-replay` | Replay the miss → catch self-correction cycle |
| `/threat-ecosystem` | Ecosystem simulation and health |
| `/nerve-arena` | Engine consensus / model tournament view |
| `/risk-orbits` | Risk visualisation |
| `/segments` | Network segments view |
| `/trophy-wall` | Sealed incidents as trophies |
| `/ledger` | Audit / compliance ledger |
| `/settings` | Configuration and connectivity status |

## Data fetching with React Query

`frontend/lib/api.ts` contains `AnvayaAPI`, a typed HTTP client, and a set of React Query hooks such as:

- `useMetrics(3000)` — fetches `/api/v1/metrics` and refetches every 3 seconds.
- `useIncidents(3000)` — fetches the incident list and refetches every 3 seconds.
- `useIncident(id)` — fetches one incident.
- `useGraph(incidentId)`, `useTrophies()`, `useBlastscopeGallery()`, etc.

React Query handles:
- **Polling** — re-fetching data automatically.
- **Caching** — not re-fetching unless data is stale.
- **Background updates** — new data appears without a full page reload.

This is why the dashboard feels "live".

## Key components

| Component | Job |
|---|---|
| `app/layout.tsx` | Root layout, dark theme, JetBrains Mono font, wraps everything in `Providers` |
| `components/providers.tsx` | Provides React Query and the global Anvaya store |
| `components/app-shell.tsx` | Common page shell: top bar, title, subtitle, sidebar |
| `components/sidebar.tsx` | Navigation with 13 links and project/session lists |
| `components/top-bar.tsx` | Header with status, clock, and ecosystem controls |
| `components/primitives.tsx` | Reusable UI pieces: `Panel`, `Bar`, `Chip`, `Dot`, `Mono` |
| `components/graph-canvas.tsx` | Renders the network graph for BlastScope |
| `lib/store.tsx` | Global client state (connected, selected incident, ecosystem mode) |
| `lib/api.ts` | All backend calls and React Query hooks |
| `lib/data.ts`, `lib/incidents.ts` | Helper data and incident grouping logic |

## Styling

- **Tailwind CSS v4** with a custom dark cyber theme.
- CSS variables for colours: `bg-canvas`, `text-cyan`, `border-hairline`, etc.
- `next.config.ts` sets `images.unoptimized: true` so the app works on static hosts without an image optimisation server.

## TypeScript

Every component is typed. The frontend uses `any` in a few places for API data because the backend is evolving, but the core UI types are strict.
