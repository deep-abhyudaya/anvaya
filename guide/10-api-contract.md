# 10 — API Contract

## Base URL

The frontend talks to the backend at:

- `NEXT_PUBLIC_API_URL` default: `http://localhost:8000/api/v1`
- Health check is at the root: `http://localhost:8000/health`

`frontend/lib/api.ts` strips the `/api/v1` suffix to call `/health` and appends it for business endpoints.

## Main endpoints

| Method | Path | Frontend caller | What it does |
|---|---|---|---|
| GET | `/health` | `store.tsx` | Server health |
| GET | `/api/v1/metrics` | `useMetrics` | Dashboard numbers |
| GET | `/api/v1/metrics/engines` | `useEngines` | Engine consensus (Nerve Arena) |
| GET | `/api/v1/metrics/trophies` | `useTrophies` | Sealed incident trophies |
| GET | `/api/v1/incidents` | `useIncidents` | List incidents with BlastScope enrichment |
| POST | `/api/v1/incidents` | `createIncident` | Create a new incident |
| GET | `/api/v1/incidents/{id}` | `useIncident` | Get one incident |
| POST | `/api/v1/incidents/{id}/transition` | `transitionIncident` | Move incident to next lifecycle state |
| GET | `/api/v1/rules` | `useRules` | List detection rules |
| POST | `/api/v1/rules` | `createRule` | Create a rule |
| GET | `/api/v1/detections` | `detections` | List detection runs |
| GET | `/api/v1/detections/{run_id}` | `detection` | Get one run |
| GET | `/api/v1/audit` | `useAuditRecords` | Sealed audit records |
| GET | `/api/v1/audit/verify` | `auditVerify` | Verify hash chains |
| GET | `/api/v1/graph/{incident_id}` | `useGraph` | Blast graph for an incident |
| GET | `/api/v1/graph/segments` | `useSegments` | Network segments |
| GET | `/api/v1/graph/reachability` | `useReachability` | Reachability list |
| GET | `/api/v1/blastscope/gallery` | `useBlastscopeGallery` | Impact gallery |
| POST | `/api/v1/blastscope/run/{incident_id}` | `blastscope` | Run BlastScope |
| POST | `/api/v1/sentinel/replay/{incident_id}` | `replay` | Replay attack with patched rule |
| POST | `/api/v1/sentinel/full-cycle/{incident_id}` | `fullCycle` | Run the full self-correction cycle |
| POST | `/api/v1/whatif/analyze/{incident_id}` | `whatif` | Counterfactual analysis |
| GET | `/api/v1/simulation/ecosystem` | `useEcosystem` | Ecosystem simulation state |
| POST | `/api/v1/demo/run` | `demo` | Run the full end-to-end demo |

## Route ordering trick

In FastAPI, routes are matched in the order they are registered. If `/{incident_id}` is registered before `/segments`, FastAPI would try to match `segments` as an incident ID. To fix this, static routes like `/graph/segments` and `/blastscope/gallery` are registered before the dynamic `/{...}` routes.

## Error handling

- Missing resource → `404 Not Found` with a JSON `detail`.
- Invalid state transition → `400 Bad Request`.
- Other server errors → `500 Internal Server Error` and logged to `structlog`.

The `AnvayaAPI` client in `frontend/lib/api.ts` throws an `APIError` object that includes method, path, status, status text, and the server detail, which helps debugging.

## OpenAPI docs

Because FastAPI auto-generates OpenAPI, you can visit `http://localhost:8000/docs` while the backend is running and try every endpoint in the browser.
