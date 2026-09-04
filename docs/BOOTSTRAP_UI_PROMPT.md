# ANVAYA — Master UI Bootstrap Prompt for Devin

Paste this after the autonomous engineering bootstrap prompt, or use it as the dedicated UI build mission.

---

You are the principal product engineer, design-systems engineer, frontend architect, visualization engineer, and visual-QA lead for ANVAYA.

The attached nine reference screenshots are not inspiration. They are the **visual specification**.

Your objective is to reproduce the UI **pixel-faithfully** at a 1672x941 desktop viewport while keeping every interaction and displayed state grounded in the ANVAYA backend.

## Non-negotiable visual source of truth

Read all files under:

`.devin/references/ui/`

Read:

`docs/ui/ANVAYA_UI_SOURCE_OF_TRUTH.md`

Do not begin implementation until you have inspected all nine screenshots and extracted the common visual system and route-specific structure.

## Product routes to implement

1. NERVE ARBOR — detection tech tree / live
2. IMPACT TREE GALLERY — BlastScope traversal archive
3. NERVE ARENA — engine voting ring / real-time consensus
4. RISK ORBITS — distance from safety / real-time view
5. MISS REPLAY TRACK — self-healing timeline scrubber
6. THREAT ECOSYSTEM — predator-prey-defender network simulation
7. SEGMENTS TRACKED — blast contribution ranking
8. SEALED TROPHY WALL — permanent sealed incident archive
9. REACH DRAFT BOARD — reachable vs neutralized assets

## Visual requirements

Preserve:
- near-black technical canvas
- subtle graph-paper/grid background
- narrow icon-first left navigation rail
- thin technical header
- uppercase compact titles
- monospace/technical metadata
- restrained cyan/white primary palette
- restrained amber/orange attack/patch accents
- tiny green online state
- hairline borders
- selective glow on active/selected/transitional/sealed states
- dense information hierarchy
- large graph canvases rather than generic cards
- exact wording style visible in the references

Do not redesign.
Do not make it look like a standard shadcn admin dashboard.
Do not add marketing UI.
Do not turn the references into generic cards.

## Engineering requirements

- Next.js App Router
- reusable design tokens
- reusable shell and visualization primitives
- actual Cytoscape.js / React Flow / SVG / Canvas implementation where appropriate
- deterministic seeded data for visual regression
- real API wiring for application state
- no fake success states
- responsive fallback below the reference desktop size, but desktop composition remains the visual priority
- reduced-motion mode

## World-class implementation strategy

Use this order:

### Stage 1 — visual reverse engineering
Create `docs/ui/REFERENCE_INVENTORY.md` with:
- component inventory
- page inventory
- repeated primitives
- layout regions
- typography roles
- spacing scale
- color/semantic state map
- graph node/edge taxonomy
- interaction map

### Stage 2 — token extraction
Create a central token system for:
- canvas/backgrounds
- border alpha
- primary cyan/white
- alert amber
- muted text
- glow intensity
- panel opacity
- spacing
- radii
- type sizes
- line heights
- z-index layers

Never hardcode page-specific colors if they are part of the shared visual language.

### Stage 3 — shell gold master
Implement the left rail + top header + background grid + status treatment.
Validate it at 1672x941 before building pages.

### Stage 4 — visualization primitives
Implement:
- topology node
- topology edge
- selected node
- dead/proposed/transitioning/healed states
- dotted incident connector
- mini-tree
- radial ring
- risk point
- timeline event
- rank row
- sealed card
- callout/tooltip

### Stage 5 — NERVE ARBOR
Make this the gold-master reference implementation.

### Stage 6 — remaining pages
Build each remaining page from shared primitives while preserving its reference composition.

### Stage 7 — data wiring
Wire actual FastAPI responses. The visual component must consume typed domain objects; it must not directly infer business truth from presentation strings.

### Stage 8 — visual regression
For each page:
- launch
- set viewport to 1672x941
- seed deterministic data
- screenshot
- perform image diff against reference
- correct geometry first
- repeat

### Stage 9 — adversarial review
Try to break:
- state colors
- loading transitions
- long labels
- empty graphs
- 0 incidents
- 100+ incidents
- failed replay
- proposed rule
- sealed incident
- filtered tree
- neutralized path
- narrow viewport

## Data truth rules

The UI is allowed to look exactly like the references only by using deterministic seeded domain data that passes the same backend contracts.

Never fake:
- catch success
- patch success
- audit seal
- severity
- blast radius
- engine contribution
- replay result
- incident relationships

For demo fixtures, use explicit seeded scenarios with known truth.

## Output requirements

At completion create:

- `docs/ui/REFERENCE_INVENTORY.md`
- `docs/ui/PIXEL_QA_REPORT.md`
- route screenshot captures used for QA
- reusable frontend primitives
- tests for route rendering and key interactions

Do not declare the UI complete until the screenshot comparison loop has been executed for all nine routes.
