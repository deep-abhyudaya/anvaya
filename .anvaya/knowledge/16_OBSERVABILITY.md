# ANVAYA — Observability

## Logging

`backend/anvaya/logging.py` uses `structlog`.

- `configure_logging(level, human=False)` sets up console or JSON logs.
- `get_logger(name)` returns a bound logger.
- `settings.log_level` controls backend verbosity.
- `settings.cli_log_level` controls CLI verbosity (default `error`).

Key log events:
- `anvaya.startup`
- `anvaya.shutdown`
- `unhandled_exception`
- `live.scoring_failed`
- `tavily.search_failed`
- `n8n.trigger_failed`
- `gmail.send_failed`
- `lyzr.propose_failed`
- `local_tool_error`
- `incident_event`

## Execution events

`backend/anvaya/agent/events.py` `EventStore`:
- Persists `ExecutionEvent` rows.
- In-memory cache for fast SSE.
- Events consumed by `/agent/executions/{id}/events` and `/stream`.

## Metrics

`backend/anvaya/routers/metrics.py`:
- Aggregate SOC KPIs over incidents, replays, rules, audit records.
- `/metrics/engines` returns hardcoded consensus scores.
- `/metrics/trophies` returns sealed incidents with artifacts.

## Health

`GET /health` in `backend/anvaya/main.py`:
```json
{"status": "healthy", "service": "anvaya", "version": "0.1.0"}
```

The frontend polls `/health` every 5s (`lib/store.tsx`).

## Tracing

No distributed tracing (OpenTelemetry, Jaeger) is currently present. Logs and events are the primary observability signals.

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/logging.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/events.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/routers/metrics.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/frontend/lib/store.tsx" />

## Active recall

- What logger does ANVAYA use?
- What does the frontend poll every 5 seconds?
- Where are execution events persisted?
- Is there OpenTelemetry tracing? (No)
