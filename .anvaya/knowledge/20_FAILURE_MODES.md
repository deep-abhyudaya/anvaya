# ANVAYA — Failure Modes

## Failure containment philosophy

- Every external integration has a truthful fallback.
- Agent tool failures are captured as `ToolResult` with `error_code`.
- `Execution` status reflects `completed`, `failed`, or `cancelled`.
- Audit records capture failure for accountability.
- No exception should crash the FastAPI process.

## Failure matrix

| Failure | Where | Cause | Containment | Recovery |
|---------|-------|-------|-------------|----------|
| No trained Alertness model | `live/__init__.py:127-134` | `engine.model is None` | Return `scored: False` | Train a model |
| `predict_single` exception | `live/__init__.py:137-144` | Feature mismatch, bad artifact | Log, return `scored: False` | Check feature columns, retrain |
| Invalid lifecycle transition | `models/incident.py:76-82` | Logic bug or wrong call | Raise `ValueError` | Validate state before call |
| Missing provider credentials | `agent/adapters.py` | Env not set | Return `fallback_used: True` | Set env, restart |
| Tavily/n8n/Gmail request fails | `agent/adapters.py` | Network/timeout/error | Return local fixture/handler | Check network/credentials |
| Agent step fails | `agent/agent_loop.py:257-267` | Engine error | If `stop_on_failure`, fail execution; else continue | Fix engine or mark step optional |
| Tool not found | `agent/executor.py:96-110` | Unknown tool name | Return `ToolResult` with `tool_not_found` | Register tool or fix plan |
| Project artifact build fails | `generations/builder.py` | Manifest step error | Retry, then fail step | Fix manifest or data |
| Subagent failure | `agent/subagents.py` | Child execution error | Emit `subagent.failed`, parent continues or fails | Inspect child execution |
| Audit chain break | `models/audit.py:99-109` | Tampering or bug | `verify_chain` returns `False` | Investigate records |
| DB locked (SQLite) | `db.py` | concurrent writes | WAL mode, retry | Use Postgres for production |
| Frontend SSE disconnect | `lib/api.ts:643` | network, server restart | Reconnect, fallback to polling | Restore backend |
| Better Auth secret missing | `auth.py` | `BETTER_AUTH_SECRET` not set | Auth validation fails | Set secret |
| CORS misconfigured | `main.py:34-51` | origin not in list | Browser blocks requests | Update `cors_origins` |
| Feature column mismatch | `ml/features.py` | event missing field | Model error | Ensure events match `FEATURE_COLUMNS` |
| Rule validation fails | `sentinel/__init__.py:239-252` | rule does not catch attacks | Incident stays `RULE_PROPOSED` | Re-propose rule |
| Replay still misses | `sentinel/__init__.py:353-368` | rule insufficient | `STILL_MISSED` → backtrack again | Iterate rule |
| BlastScope origin not found | `blastscope/__init__.py:76-84` | host not in asset graph | Synthetic `ORIGIN-{id}` created | Add assets if needed |
| LLM plan invalid | `agent/planner.py` | model returns bad JSON | Fall back to `DeterministicPlanner` | Fix model or use local planner |
| Execution cancelled | `agent/agent_loop.py:179-184` | user cancel | Exit loop, status `cancelled` | Resume or rerun |
| Model provider timeout | `llm/providers.py` | slow external API | `resolve_planner` falls back to deterministic | Check provider status |

## Important error codes

From `LocalToolExecutor` and `AgentLoop`:

- `tool_not_found`
- `execution_error`
- `backtrack_failed`
- `propose_failed`
- `step_failed`
- `missing_incident`
- `project_not_found`

## Logging

`backend/anvaya/logging.py` uses `structlog`:

- Backend logs: `info` / `debug` level.
- CLI logs: `error` by default, human-readable.
- Key log keys: `error`, `tool`, `incident_id`, `execution_id`, `provider`, `fallback_used`.

## Where to look first when debugging

| Symptom | First file |
|---------|------------|
| Frontend not loading data | `frontend/lib/api.ts`, `backend/anvaya/main.py` CORS |
| Agent not starting | `backend/anvaya/routers/agent.py`, `backend/anvaya/agent/orchestrator.py` |
| Tool fails | `backend/anvaya/agent/executor.py` |
| No live detections | `backend/anvaya/live/__init__.py`, `ml/anvaya/alertness/__init__.py` |
| Events not streaming | `backend/anvaya/agent/events.py`, `backend/anvaya/routers/agent.py` |
| Build stuck | `backend/anvaya/generations/builder.py` |
| Rule not catching | `backend/anvaya/sentinel/__init__.py` |
| External provider silent | `backend/anvaya/agent/adapters.py` |
| Audit chain fails | `backend/anvaya/models/audit.py` |

## Active recall

- What happens when `AlertnessEngine` has no model loaded?
- What does `fallback_used: True` mean and where is it set?
- How does the agent loop handle a failed step?
- What is the first thing to check if the frontend cannot reach the backend?
- What does `verify_chain` detect?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/live/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/executor.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/agent_loop.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/audit.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/logging.py" />
