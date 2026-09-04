# 04 — Backend: FastAPI

## What is FastAPI?

FastAPI is a modern Python web framework. It is fast, automatically creates OpenAPI / Swagger documentation, and uses Python type hints to validate request and response data.

## Entry point

`backend/anvaya/main.py` creates the FastAPI app and registers all routers.

Key pieces in `main.py`:

- `lifespan` — runs when the server starts. It configures logging and calls `init_db()` to create SQLModel tables.
- `FastAPI(...)` — the app object with title, description, version, and lifespan.
- CORS middleware — lets the Next.js frontend talk to the backend.
- Security headers — `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`.
- Global exception handler — logs errors and returns a clean 500 response.
- `/health` — root health check.
- Routers registered under `/api/v1`.

## Domain routers

Each router is a separate file in `backend/anvaya/routers/`. They group related endpoints:

| Router file | Base path | What it does |
|---|---|---|
| `incidents.py` | `/api/v1/incidents` | List, create, get, transition, self-correct incidents |
| `telemetry.py` | `/api/v1/telemetry` | Ingest and query telemetry events |
| `detections.py` | `/api/v1/detections` | Run and retrieve detection runs |
| `rules.py` | `/api/v1/rules` | List, get, create detection rules |
| `replay.py` | `/api/v1/replay` | Replay run records |
| `sentinel.py` | `/api/v1/sentinel` | Backtrack, propose, validate, replay, full cycle |
| `blastscope.py` | `/api/v1/blastscope` | Run and get blast-radius analysis |
| `whatif.py` | `/api/v1/whatif` | Counterfactual risk analysis |
| `audit.py` | `/api/v1/audit` | Audit records and chain verification |
| `graph.py` | `/api/v1/graph` | Graph nodes, edges, segments, reachability |
| `metrics.py` | `/api/v1/metrics` | Dashboard aggregate metrics, engine consensus, trophies |
| `models.py` | `/api/v1/models` | ML model versions |
| `datasets.py` | `/api/v1/datasets` | Dataset generation and metadata |
| `simulation.py` | `/api/v1/simulation` | Ecosystem simulation |
| `demo.py` | `/api/v1/demo` | Orchestrator that runs the full lifecycle |

## FastAPI technical terms

- **Path operation** — the Python function decorated with `@router.get(...)`, `@router.post(...)`, etc.
- **Path parameter** — `{incident_id}` in `/incidents/{incident_id}`. FastAPI passes it as a function argument.
- **Query parameter** — `?status=sealed` in the URL. FastAPI can read it from function arguments.
- **Dependency injection** — `session: Session = Depends(get_session)`. FastAPI calls `get_session()` for each request and gives the same database session to the route.
- **Pydantic model** — a Python class that describes the shape of request and response JSON. ANVAYA uses Pydantic both directly and through SQLModel.
- **OpenAPI / Swagger** — auto-generated interactive docs at `/docs`.

## Configuration

`backend/anvaya/config.py` uses `pydantic-settings` to load settings from environment variables and a `.env` file. Key settings:

- `database_url` — PostgreSQL or SQLite connection string.
- `openai_api_key` / `openai_model` — optional LLM support.
- `api_host` / `api_port` — where the server listens.
- `debug` — toggles CORS and logging.
- `isolation_forest_*` — ML hyperparameters.

## CLI

`backend/anvaya/cli/typer_app.py` (exposed as the `anvaya` console entry point after `pip install -e ".[dev]"`) has commands such as:

- `serve` — run the FastAPI / Uvicorn server.
- `demo` — run the full self-correction demo.
- `init-db` — initialise the database.

## Logging

`backend/anvaya/logging.py` uses `structlog` to output structured JSON-style logs. Each engine has a named logger, e.g. `anvaya.sentinel`.
