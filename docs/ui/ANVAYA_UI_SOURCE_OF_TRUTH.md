# ANVAYA UI — Pixel-Faithful Source of Truth

## 0. Purpose

The nine reference images in `.devin/references/ui/` are the visual source of truth for the ANVAYA dashboard. The goal is a **pixel-faithful reconstruction**, not a generic cyber-SOC interpretation.

Do not redesign, modernize, simplify, substitute, or "improve" the visual language unless explicitly instructed by the user. Preserve the exact information hierarchy, composition, density, dark palette, typography character, sidebar structure, panel geometry, graph treatment, labels, microcopy style, glowing states, and relative spacing shown in the references.

"Same to same" means:
- same overall 16:9 composition at desktop breakpoint
- same left navigation rail width and placement
- same top header geometry
- same content grid and panel proportions
- same dark near-black background and faint technical grid
- same thin-line borders
- same cyan/white primary emphasis with restrained amber/orange alert accents
- same small monospace/technical labels
- same hierarchy and density
- same graph/timeline/card geometry
- same interaction states represented visually
- same visual rhythm and negative space

Exact pixel equality can only be judged at the rendered browser viewport, so every page must be validated against the supplied reference screenshot at 1672x941.

## 1. Reference Set

1. `01-detection-tree.png` — NERVE ARBOR / detection tech tree / live
2. `02-impact-tree-gallery.png` — IMPACT TREE GALLERY / BlastScope traversal archive
3. `03-nerve-arena.png` — NERVE ARENA / engine voting ring / real-time consensus
4. `04-risk-orbits.png` — RISK ORBITS / distance from safety / real-time view
5. `05-miss-replay-track.png` — MISS REPLAY TRACK / self-healing timeline scrubber
6. `06-threat-ecosystem.png` — THREAT ECOSYSTEM / predator-prey-defender network simulation
7. `07-segments.png` — tracked network segments / blast contribution ranking
8. `08-trophy-wall.png` — SEALED TROPHY WALL / permanent record of sealed incidents
9. `09-reach-board.png` — REACH DRAFT BOARD / reachable vs neutralized assets

## 2. Global Visual System

### Canvas
- Desktop-first, 1672x941 reference viewport.
- Entire application sits inside the viewport without accidental browser-scroll gutters.
- Background is visually near-black, not pure black.
- Add a very subtle technical grid/scan texture across graph-heavy surfaces.
- Keep contrast restrained: no large saturated surfaces.

### Navigation rail
- Fixed left rail on every desktop page.
- Narrow, dense, icon-first navigation.
- White/cyan active icon and label treatment.
- Thin vertical separators.
- Small analyst presence/status block near the bottom.
- Preserve exact section ordering as depicted in each reference.
- Active item is emphasized by a subtle luminous boundary/accent, not a large filled tab.

### Top header
- Thin horizontal header.
- Uppercase/technical title at left.
- Breadcrumb or slash-separated context where shown.
- Small status metrics aligned toward the right.
- Tiny green online/status indicator where shown.
- Header is dense and calm; it must never become a conventional SaaS navbar.

### Typography
- Favor a technical/monospaced display character for dashboard metadata and small labels.
- Headings use compact uppercase lettering.
- Body labels are small and precise.
- Numeric telemetry uses tabular/monospace-friendly treatment.
- Avoid rounded playful fonts, oversized marketing typography, or modern consumer-dashboard styling.

### Color semantics
- Primary information: pale cyan / cool white.
- Secondary information: muted grey.
- Warning, attack origin, compromised, or patching states: restrained amber/orange.
- Status/online: small green.
- Dead/filtered/proposed states: dark grey with reduced opacity.
- Do not introduce purple, blue gradients, rainbow status colors, or generic Tailwind color palettes.

### Surfaces and borders
- Panels are mostly transparent/near-black with hairline borders.
- Corner radii are small and subtle.
- Avoid heavy card shadows.
- Use luminous edge glows only for selected, active, transitional, or sealed elements.
- Do not turn every element into a glowing neon card.

### Motion
- Motion should communicate system state rather than decoration.
- Use subtle pulse/glow for live nodes, replay cursor, active incidents, and selected cards.
- Graph transitions are smooth but restrained.
- Avoid bouncy micro-interactions.
- All animation must have reduced-motion support.

## 3. Shared Application Shell

Every route should use the same shell:

`AppShell`
- `Sidebar`
- `TopTelemetryBar`
- `PageCanvas`
- page-specific graph/card surface
- optional status/footer strip

The shell must not remount unnecessarily when navigating between pages. Preserve route-level visual continuity.

## 4. Page Definitions

### 4.1 NERVE ARBOR — Detection Tech Tree

Reference: `01-detection-tree.png`

Composition:
- Left navigation rail.
- Header: `NERVE ARBOR / DETECTION TECH TREE / LIVE`.
- Small right-side header telemetry showing miss → patch → catch cycles, SOC node, time, online dot.
- Large central node graph.
- Bottom-center `ANVAYA CORE` root node.
- Branches radiate upward to detection nodes.
- Nodes have semantic states:
  - healed/caught
  - proposed
  - transitioning
  - dead logic
  - incident-origin scar
- Incident relationships appear as dotted amber connectors toward the right-side incident stack.
- Right sidebar contains `RULE DETAIL`, `BRANCH HEALTH`, and `CYCLE HISTORY`.
- Bottom legend explains all node/link states.

Behavior:
- Hovering a node reveals exact rule metadata.
- Selecting a rule updates right panel without changing page geometry.
- Patching state visually transitions the selected node from proposed/transitioning to healed only after validation and replay success.
- Incident links are rendered from real backend relationships; never hardcode visually convenient lines.

### 4.2 IMPACT TREE GALLERY

Reference: `02-impact-tree-gallery.png`

Composition:
- Header title and subtitle.
- Filter tabs: `ALL`, `PAYROLL`, `CUSTOMER DB`, `IDENTITY`.
- Legend for contained/sealed, ignored/uncontained, filtered.
- Dense three-row gallery of incident cards.
- Each card is a miniature topology tree with depth and reach text.
- Selected card has a stronger cyan frame/glow and contextual tooltip.
- Orange incidents indicate uncontained/ignored impact.
- Bottom status row shows count/filter and `VIEW FULL TREE` control.

Behavior:
- Card filter state is functional.
- Mini tree must be generated from the same graph data as the detailed tree page.
- Hover/select preserves compact card geometry.

### 4.3 NERVE ARENA

Reference: `03-nerve-arena.png`

Composition:
- Title: `NERVE ARENA`.
- Subtitle: engine voting ring / real-time consensus.
- Main centered circular severity gauge.
- Four engines placed around it:
  - SENTINEL
  - BLASTSCOPE
  - LEDGER
  - WHAT-IF
- Engine contribution labels show normalized score and percentage.
- Center shows severity and consensus.
- Small callout for contribution/counterfactual count.
- Bottom segmented controls: `BEFORE BLAST`, `AFTER BLAST`, `AFTER COUNTERFACTUALS`.

Behavior:
- Ring segments are driven by actual engine outputs.
- Do not fabricate percentages for presentation; compute them from current incident data.
- State toggle recomputes center severity from the selected stage.

### 4.4 RISK ORBITS

Reference: `04-risk-orbits.png`

Composition:
- Radial chart centered on `SAFE`.
- Concentric rings labeled LOW / MEDIUM / HIGH / CRITICAL.
- Incidents appear as small points around the radial field.
- Certain points show muted subject icons.
- Hotspot density is shown subtly.
- Right legend explains active incident, lower severity, sealed/frozen, current movement, counterfactual, density hotspot.
- Top metrics show active, sealed, critical counts and a period selector.

Behavior:
- Risk placement must derive from incident severity/risk.
- Sealed incidents remain visually frozen.
- Counterfactual paths use dashed connectors.
- Hover reveals incident identity and risk metadata.

### 4.5 MISS REPLAY TRACK

Reference: `05-miss-replay-track.png`

Composition:
- Header: `MISS REPLAY TRACK` with subtitle `self-healing timeline scrubber`.
- Incident/host/user telemetry line.
- Horizontal event timeline:
  - process spawn
  - MISS
  - ground truth: compromise confirmed
  - rule proposed
  - RE-RUN: caught
- Two comparison lanes:
  - PRE-PATCH (before fix)
  - POST-PATCH (after fix)
- Vertical rule-proposal marker crosses both lanes.
- Bottom replay controls and scrubber.

Behavior:
- Replay is not cosmetic. Timeline position, event highlighting, and lane states correspond to actual replay records.
- Scrubbing changes the visual time state.
- Play/pause, step back/forward, speed, and replay selector are functional.
- The post-patch lane must not show a caught state until actual replay succeeds.

### 4.6 THREAT ECOSYSTEM

Reference: `06-threat-ecosystem.png`

Composition:
- Header: `THREAT ECOSYSTEM` and subtitle predator-prey-defender network simulation.
- Top-right mode toggle: IGNORE / CONTAIN.
- Top-center ecosystem health percentage.
- Full-canvas network graph with attacker, defender, and asset nodes.
- Orange dashed attacker edges.
- White/cyan normal graph edges.
- Defender nodes are hexagonal.
- Threat/attacker nodes are diamond-like orange markers.
- Central highlighted defender node has luminous treatment.
- Tooltip/callout explains defender role and blocked paths.
- Bottom simulation step control.

Behavior:
- Simulation step is deterministic and synchronized to backend simulation events.
- IGNORE/CONTAIN changes simulation strategy and recomputes result.
- Graph node types and edges must be data-driven.

### 4.7 SEGMENTS TRACKED

Reference: `07-segments.png`

Composition:
- Header metrics: segments tracked and top traffic segment.
- Split layout:
  - left graph canvas
  - right ranked segment list
- Left graph highlights hot segments and baseline segments.
- Right list has six ranked entries, each with:
  - rank
  - segment name
  - depth/reach
  - traffic score bar
  - status/risk indicator
- Selected segment produces a contextual tooltip over graph.

Behavior:
- Ranking must be computed from graph metrics.
- Selecting a row highlights its path in the graph.
- Neutralized segments visibly lose emphasis without disappearing.

### 4.8 SEALED TROPHY WALL

Reference: `08-trophy-wall.png`

Composition:
- Header: `SEALED TROPHY WALL`.
- Subtitle explains permanent record / computed rarity.
- Top filter tabs: ALL / REPAIRED MISSES / FULL COVERAGE.
- Top-right metrics: sealed incidents and max complexity.
- Large horizontal incident cards grouped by severity tier.
- Selected/recent incidents have stronger luminous frames.
- Cards display engines, max severity, blast radius, seal time, controls.
- Footer explains rarity encoding.
- Auto-refresh indicator on bottom-right.

Behavior:
- Rarity is computed from engines fired × blast radius, matching the visual concept.
- Sealed means immutable UI state; historical records must not appear editable.
- Filters are functional.

### 4.9 REACH DRAFT BOARD

Reference: `09-reach-board.png`

Composition:
- Header: `REACH DRAFT BOARD`.
- Top counts: reachable and neutralized.
- Attack / Defense toggle.
- Large ranked list of assets.
- Every row contains:
  - rank
  - asset name
  - state badge
  - hop count
  - impact score bar
  - numeric score
- Hover/selection shows graph adjacency context.
- Right-side callout shows adjacency data.
- Disabled/neutralized row is visually muted.

Behavior:
- Rankings update from current graph/simulation data.
- Attack mode prioritizes reachable/compromisable assets.
- Defense mode prioritizes neutralization opportunities.

## 5. Components

Build reusable components before page-specific implementations:

- `AnvayaShell`
- `NerveSidebar`
- `TelemetryHeader`
- `SectionLabel`
- `MonoMetric`
- `StateDot`
- `GlowFrame`
- `IncidentCard`
- `MiniTopology`
- `TopologyGraph`
- `EngineContributionRing`
- `RiskOrbitChart`
- `ReplayTimeline`
- `ReplayControls`
- `ImpactTreeCard`
- `RankedSegmentList`
- `AssetReachRow`
- `SealedIncidentCard`
- `StatusLegend`
- `DataCallout`
- `Tooltip`

Centralize design tokens rather than scattering arbitrary values throughout pages.

## 6. Data Integrity Rules

Visual states MUST map to backend facts:

- `CAUGHT` = replay actually detected the attack.
- `PATCH APPLIED` = a candidate rule was persisted and validated.
- `SEALED` = immutable audit state is complete.
- `CONTAINED` = simulation/response state says contained.
- `PROPOSED` = rule exists but is not yet validated.
- `TRANSITIONING` = execution is in progress.
- `DEAD LOGIC` = rule has no successful detection history.

Never use fake values merely to make screenshots look right in production/demo mode. Seed data may be deterministic, but it must still pass the same rendering paths.

## 7. Pixel-Fidelity QA Protocol

For each route:

1. Start the app at exactly 1672x941 viewport.
2. Render with seeded data corresponding to the reference.
3. Capture screenshot.
4. Compare against the supplied reference image.
5. Check, in order:
   - global shell
   - sidebar width
   - header height
   - major panel geometry
   - node/card positions
   - typography scale
   - border/glow intensity
   - spacing
   - labels and microcopy
   - legends and footer controls
6. Fix the largest geometric mismatch first.
7. Re-capture.
8. Repeat until the page is visually indistinguishable at normal viewing scale.

Use image-diff tooling when available. Do not judge fidelity only by source-code inspection.

## 8. Anti-Drift Constraints

DO NOT:
- replace the dark technical aesthetic with a generic dashboard
- add rounded colorful cards
- use standard shadcn default styling without overriding it
- introduce large hero sections
- add marketing copy to product screens
- invent extra navigation items
- change the sidebar order casually
- replace graphs with generic placeholder charts
- make everything neon
- enlarge typography for readability at the expense of composition
- change labels to more conventional SaaS terminology
- substitute mock graphs when the reference clearly uses a structural topology

When visual or functional requirements conflict, preserve both by separating data logic from presentation logic; do not delete a reference element to simplify implementation.
