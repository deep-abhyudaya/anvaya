# ANVAYA API Contract

This document is the source of truth for the HTTP contract between the Next.js 15
frontend and the FastAPI backend. All frontend calls live in `frontend/lib/api.ts`.

## Base URLs

- `NEXT_PUBLIC_API_URL` (default: `http://localhost:8000/api/v1`) is the base for
  all business endpoints.
- Health is exposed as an infrastructure endpoint at the **root** of the backend
  host: `http://localhost:8000/health`.

The frontend connectivity probe strips `/api/v1` from `NEXT_PUBLIC_API_URL` and
calls the resulting root base.

## Route table

| Method | Path | Purpose | Frontend caller |
|--------|------|---------|----------------|
| GET | `/health` | Infrastructure health check | `store.tsx` connectivity probe |
| GET | `/api/v1/metrics` | Dashboard metrics | `useMetrics` |
| GET | `/api/v1/metrics/engines` | Nerve Arena consensus | `useEngines` |
| GET | `/api/v1/metrics/trophies` | Trophy wall data | `useTrophies` |
| GET | `/api/v1/incidents` | List incidents | `useIncidents` |
| POST | `/api/v1/incidents` | Create incident | `createIncident` |
| GET | `/api/v1/incidents/{id}` | Get incident | `useIncident` |
| POST | `/api/v1/incidents/{id}/transition` | Lifecycle transition | `transitionIncident` |
| GET | `/api/v1/rules` | List detection rules | `useRules` |
| GET | `/api/v1/rules/{id}` | Get rule | `useRule` |
| POST | `/api/v1/rules` | Create rule | `createRule` |
| GET | `/api/v1/detections` | List detection runs | `detections` |
| GET | `/api/v1/detections/{run_id}` | Get detection run | `detection` |
| GET | `/api/v1/detections/{run_id}/results` | Run results | — |
| GET | `/api/v1/audit` | Sealed audit records | `useAuditRecords` |
| GET | `/api/v1/audit/verify` | Verify per-incident hash chains | `auditVerify` |
| GET | `/api/v1/audit/{record_id}` | Single audit record | `getAuditRecord` |
| GET | `/api/v1/graph/segments` | Segment ranking (static) | `segments` |
| GET | `/api/v1/graph/reachability` | Reachability assets (static) | `reachability` |
| GET | `/api/v1/graph/{incident_id}` | Blast graph for incident | `graph` |
| GET | `/api/v1/blastscope/gallery` | Impact gallery incidents | `blastscopeGallery` |
| POST | `/api/v1/blastscope/run/{incident_id}` | Run BlastScope | `blastscope` |
| GET | `/api/v1/blastscope/{incident_id}` | BlastScope result | `blastscope` (GET) |
| POST | `/api/v1/sentinel/replay/{incident_id}` | Replay scenario | `replay` |
| POST | `/api/v1/sentinel/full-cycle/{incident_id}` | Full self-correction | `fullCycle` |
| POST | `/api/v1/whatif/analyze/{incident_id}` | Counterfactual analysis | `whatif` |
| GET | `/api/v1/simulation/ecosystem` | Ecosystem simulation | `useEcosystem` |
| GET | `/api/v1/agent/tools` | List agent tools | `useAgentTools` |
| POST | `/api/v1/agent/execute?background=true` | Start an agent execution | `agentExecute` |
| GET | `/api/v1/agent/profiles` | List agent profiles | `useAgentProfiles` |
| GET | `/api/v1/agent/models` | List model configs | `useAgentModels` |
| GET | `/api/v1/agent/providers` | Provider health status | `useAgentProviders` |
| GET | `/api/v1/agent/executions` | List executions | `useAgentExecutions` |
| GET | `/api/v1/agent/executions/{id}` | Get execution | `agentExecution` |
| GET | `/api/v1/agent/executions/{id}/events` | Execution events | `useAgentEvents` |
| GET | `/api/v1/agent/executions/{id}/context` | Live execution context | `useAgentContext` |
| POST | `/api/v1/agent/executions/{id}/message` | Append user message | `postExecutionMessage` |
| POST | `/api/v1/agent/executions/{id}/cancel` | Cancel execution | `cancelExecution` |
| GET | `/api/v1/agent/executions/{id}/stream` | SSE stream (reconnect with `?after=`) | `useAgentStream` |
| GET | `/api/v1/agent/subagents/profiles` | List subagent profiles | `useSubagentProfiles` |
| GET | `/api/v1/agent/subagents` | List subagents | `useSubagents` |
| POST | `/api/v1/agent/subagents` | Spawn a subagent | `spawnSubagent` |
| GET | `/api/v1/agent/subagents/{id}` | Get subagent | `subagent` |
| POST | `/api/v1/agent/subagents/{id}/cancel` | Cancel subagent | `cancelSubagent` |
| POST | `/api/v1/agent/subagents/{id}/resume` | Resume subagent | `resumeSubagent` |
| GET | `/api/v1/agent/executions/{id}/subagents` | Subagents of an execution | `executionSubagents` |
| POST | `/api/v1/demo/run` | Run end-to-end demo | `demo` |

## 404 fixes

The following collisions/mismatches were fixed so that the contract above is
honored:

1. **Health endpoint** — the frontend previously called `/api/v1/health`, which
   did not exist. The backend keeps `/health` as a root infrastructure endpoint
   and the frontend now derives the root base from `NEXT_PUBLIC_API_URL`.

2. **Graph static routes** — `/api/v1/graph/segments` and
   `/api/v1/graph/reachability` were shadowed by `/api/v1/graph/{incident_id}`.
   Static routes were moved before the dynamic path parameter in
   `backend/anvaya/routers/graph.py`.

3. **BlastScope gallery** — `/api/v1/blastscope/gallery` was shadowed by
   `/api/v1/blastscope/{incident_id}`. The gallery route was moved before the
   dynamic route in `backend/anvaya/routers/blastscope.py`.

4. **Missing detection run route** — `GET /api/v1/detections/{run_id}` was added
   to match the frontend `AnvayaAPI.detection(id)` helper.

5. **Graph path vs query** — `AnvayaAPI.graph` previously used
   `/graph?incident_id=...`, which had no backend route. It now calls
   `/api/v1/graph/{incident_id}`.

## Response shapes

### `GET /api/v1/incidents`

Returns `{ items: [...], total, limit, offset }`. Each incident is enriched with:

- `blastRadius`: real `blast_radius_score` from the incident, falling back to
  `BlastRadiusResult.impact_score` if available.
- `hops`: `BlastRadiusResult.max_depth` for the incident, or `0`.

These extra keys power the impact gallery cards.

### `GET /api/v1/metrics/trophies`

Returns `{ items: [...] }` for sealed incidents. Each trophy contains:

- `id`, `status`, `title`, `severity`, `host`, `user`
- `blastRadius`, `hops`, `counterfactuals`, `controls`
- `engines`: `{ sentinel, blastscope, whatif, ledger }` derived from persisted
  replay, blast-scope, what-if and audit records.
- `sealedAt`, `started` as `HH:MM` strings.

### `GET /api/v1/audit`

When no `incident_id` filter is supplied, returns sealed records only
(`action == "incident_sealed"`). Each record is enriched with:

- `controls_satisfied`: count of unique control mappings for the incident.
- `blast_radius`: the incident's blast radius score.
- `engines`: the same four-engine object used by trophies.

### `GET /api/v1/graph/segments`

Returns `{ items: [...], nodes: [...], extra_edges: [...] }`.

### `GET /api/v1/graph/reachability`

Returns `{ items: [...] }`.

### `GET /api/v1/blastscope/gallery`

Returns `{ items: [...] }`.

### `GET /api/v1/audit/verify`

Returns:

```json
{
  "valid": true,
  "record_count": 36,
  "incident_count": 4,
  "details": [
    { "incident_id": "...", "valid": true, "record_count": 9 }
  ]
}
```

The backend verifies each incident's hash chain independently.

## Error behavior

- Missing single resources (incident, blast scope result, audit record,
  detection run) return `404 Not Found` with a JSON `detail`.
- Empty collections return `200 OK` with `{ items: [] }`.
- Invalid state transitions return `400 Bad Request`.
- The API client in `frontend/lib/api.ts` throws an `APIError` containing
  `method`, `path`, `status`, `statusText` and `detail` for non-2xx responses.

## Demo integrity

`POST /api/v1/demo/run` and `anvaya demo` run the full
`miss → ground_truth → backtrack → propose → validate → replay → caught →
blastscope → whatif → seal` lifecycle. Audit records are now linked per-incident,
so the per-incident chain validates successfully (`Audit Valid: True`).

## Known caveats

- Audit records created before the per-incident chain fix may still be invalid
  when verified globally. New demo runs create valid per-incident chains.
- The BlastScope `max_depth` may be `0` for incidents with no graph assets.
  This is real data, not a default.
