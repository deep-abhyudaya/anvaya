# Artifact Build Experience — Assumptions

## Goal
Transform ANVAYA from an instant artifact generator into a visible, sequential product builder where the AI assembles artifacts in front of the user.

## Current state

- **Frontend build state** is centralized in `AgentProvider` (`frontend/components/agent/agent-context.tsx`).
  - `build` holds the `ArtifactBuildState`.
  - A single navigation effect observes `build.navigateTo` and routes the user once when the builder announces the target page.
  - `useArtifactBuild` is now a thin selector over `AgentProvider`; it no longer runs its own EventSource.

- **Build event reducer** lives in `frontend/lib/build.ts`.
  - `applyBuildEvent` maps backend events (`generation.*`, `navigation.*`, `artifact.*`, `element.*`) to state updates.
  - `buildMountedElements<T>` extracts the mounted elements from a running build so pages can render rows/nodes/trophies as they land.

- **Backend manifest system** in `backend/anvaya/generations/manifests.py` now has named manifests for every `ARTIFACT_TYPES` entry:
  - `ORBITS_MANIFEST` and `INCIDENTS_MANIFEST` are fully specified.
  - `ARBOR_MANIFEST`, `IMPACTS_MANIFEST`, `REACH_MANIFEST`, `REPLAY_MANIFEST`, `ECOSYSTEM_MANIFEST`, `ARENA_MANIFEST`, `SEGMENTS_MANIFEST`, `TROPHY_WALL_MANIFEST`, and `LEDGER_MANIFEST` have been added.
  - A generic three-step fallback manifest handles unknown artifact types.

- **Per-element construction** in `backend/anvaya/generations/builder.py`.
  - After each manifest step creates its payload slice, `_emit_element_events` emits `element.thinking` and `element.mounted` for list-like data.
  - Manifest steps can set `elements_from` / `element_id_field`; otherwise the builder auto-detects list fields in the delta.

- **Agent chat path** in `backend/anvaya/agent/executor.py` delegates `handle_generate_artifacts` to `handle_manage_artifacts`, so artifact generation triggered from the agent console uses the same staged builder and stream.

- **Dashboard build flow** in `frontend/app/dashboard/page.tsx` remains the entry point. The single `AgentProvider` now owns navigation, so duplicate listeners in `BuildListener`/`BuildPanel` were removed.

- **Page-level integration** in every artifact page (`frontend/app/<artifact>/page.tsx`) now:
  - Reads `?build=<execution_id>` from the URL.
  - Subscribes to the build via `useArtifactBuild`.
  - Shows `BuildStatus` and `BuildTimeline` while the build is running.
  - Renders `buildMountedElements(...)` incrementally and falls back to `useProjectArtifactLatest` once the build completes or when no build is active.
  - Wraps `useSearchParams` in a `Suspense` boundary and exports `dynamic = "force-dynamic"` where needed.

## Technical approach
- Underlying generation remains `ArtifactGenerator` building the full payload once.
- `ArtifactBuilder` walks the manifest, persists per-step `GenerationArtifact` rows, publishes cumulative payload slices to `ProjectArtifactPayload`, and emits the event stream.
- The UI is driven by the SSE stream from `/agent/executions/{id}/stream`; React Query continues to refetch the latest payload in the background.

## Resolved / current decisions

- **Project vs. incident scope** is now kept distinct. `Execution.incident_id` is only populated for real incident investigations; project-scoped artifact runs use `ExecutionContext.project_id` and the API response returns `project_id` separately. This prevents the agent console header from mislabeling a project as an incident.
- **Artifact type → route mapping** is centralized in `backend/anvaya/routes.py` and mirrored in `frontend/lib/routes.ts`. The builder embeds `route` in build events, and `artifact.created` carries a real `link` to the target page.
- **Think-then-act pacing** is controlled by `STEP_THINK_PAUSE` and `ELEMENT_THINK_PAUSE` in `backend/anvaya/generations/builder.py`. `artifact.thinking` and `element.thinking` now publish `purpose`/`reason`, and the UI's `ReasoningCard` + `CurrentActionCard` show the current thought before the matching element appears.
- **Stable element ids** are emitted as `step_id` / `element_id` and surfaced on the page as `id` attributes on `BuildTimeline` rows, incident table rows, and orbit SVG nodes/edges.
- **Build completion status** is derived from the artifact counter, not just the `generation.completed` label, so the status banner and counter stay consistent.

## Open questions / future work
- The exact human labels and selectors for every new manifest should be validated against real payloads once larger datasets are tested.
- For very large element lists, the current per-element event emission may need batching to keep event counts reasonable.

## Model provider integration

- **SeekAI (`seekai`)** is treated as a gateway, not a model maker. The base URL is `https://seekai.cc/v1` and the protocol is OpenAI-compatible. Live `GET /v1/models` IDs are merged into the static catalog: IDs returned by the live endpoint are marked `available`, and any live IDs not in the user-supplied catalog are added as `available` so the full set the key can reach is visible.
- **GMI Cloud (`gmicloud`)** is an OpenAI-compatible inference gateway at `https://api.gmi-serving.com/v1`. Discovery is live; when a key is configured, every chat/instruct model returned by `GET /v1/models` is surfaced. A small static fallback preserves `MiniMax-M3` and `MiniMax-M2.7` as `unavailable` when no key is present.
- **Empero (`empero`)** is a public community endpoint at `https://free.empero.org/v1`. No user secret is required (`free` token). Models are always `public_community_endpoint` and the UI warns that prompts are logged. `Qwen/Qwen3.8-27B-FP8` is included from provider documentation even though it did not appear in the live `/v1/models` list.
- New `ModelConfig` fields (`pricing_mode`, `cost_per_request`, `access_class`, `privacy_class`, `gateway_type`, `aliases`, `max_tokens`) are optional and backward-compatible. Existing providers default to `standard` / `per_token` values.

## Agent console Markdown rendering

- `react-markdown@^10.1.0` with `remark-gfm` and `rehype-sanitize` is the rendering pipeline for all agent/chat assistant messages. Syntax highlighting is performed client-side with `shiki/core` and the JavaScript regex engine for synchronous, streaming-safe operation.
- `rehype-sanitize` uses its default GitHub-style schema; `code` language classes are preserved by default, so `pre` components can extract the language and pass it to the highlighter.
- Code blocks are not highlighted while a message is streaming; they render as plain monospaced text and snap to highlighted output once the stream completes. This avoids per-chunk re-highlighting cost and incomplete-fence parsing issues.
- Proportional body text is rendered with an added `Inter` font while headings and code retain the console monospace character.
- Composer actions (`start`, `chatStream`, `sendFollowUp`) now return a boolean success flag; `AgentConsole` only clears input/context on success, preserving the user's text when a submission fails.

## Frontend route consolidation (4-route bento dashboard) — Aug 31 2026

- **Goal:** Compress the 11 previous per-artifact Next.js routes into 4 category routes (`/sentinel`, `/pathfinder`, `/responder`, `/auditor`) for a 5-minute hackathon demo, while reusing every existing data hook and visualization unchanged.
- **Groupings used (per product owner):**
  - `/sentinel`: overview, incidents, risk-orbits
  - `/pathfinder`: reach-board, segments, threat-ecosystem
  - `/responder`: miss-replay, nerve-arena, impact-gallery
  - `/auditor`: trophy-wall, ledger, history
- **Open decisions / conservative defaults:**
  1. **AgentConsole placement:** Kept global/unchanged via the existing `app-shell.tsx`. No per-page AgentConsole tile.
  2. **History and Settings:** `history` becomes a tile inside `/auditor` as spec'd; `settings` remains a separate top-level nav item (unmerged) and is not added to any category page.
  3. **Old deep links:** Legacy routes (e.g. `/incidents`) are kept as redirect stubs that preserve query params (`?build=...`) and route to `/<category>#<tile-id>` (e.g. `/sentinel#incidents`). The target tile is briefly highlighted and scrolled into view on load.
- **Cross-tile coupling preserved:**
  - `segments` graph and ranked-list selection/hover continue to share the same `state.segments.selected` store state inside the single `segments-tile`.
  - `overview` incident row links, `lib/incidents.ts` `openIncident`, and `sidebar.tsx` `SessionsSection` routing are updated to the new category routes so navigation stays coherent.
- **Backend route map (`backend/anvaya/routes.py`):** Not modified per explicit scope. Build-time `navigation.*` events still carry the legacy route strings; the frontend redirects convert those URLs to the new category routes while preserving the build query parameter.

## Mixed investigation + artifact-generation objectives

- A mixed objective (e.g. "investigate INC-XXXX and rebuild orbits and the impact gallery") is routed to a single combined plan.
- When the objective does not explicitly order the two halves, the agent defaults to **investigation first, artifact generation second**. This keeps the incident context fresh before the agent builds artifacts and matches the typical SOC workflow.
- The combined plan is executed by `AgentLoop.run_investigation`, which is tool-agnostic: each `manage_artifacts` step is narrated the same way as an investigation tool step.
