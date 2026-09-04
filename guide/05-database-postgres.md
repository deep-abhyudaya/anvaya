# 05 — Database: PostgreSQL and SQLModel

## What is SQLModel?

SQLModel is a library by the FastAPI team. It combines **Pydantic** (data validation) and **SQLAlchemy** (database ORM) into one class. A `SQLModel` class can describe a database table and also be used as a Pydantic response model.

## Database engine

`backend/anvaya/db.py` creates the SQLAlchemy engine from `settings.database_url`. On startup, `init_db()` imports all model modules and calls `SQLModel.metadata.create_all(engine)` to create the tables.

For development, the default is `sqlite:///./anvaya.db`. For production, set `DATABASE_URL` to a PostgreSQL connection string.

## Sessions

`get_session()` is a Python generator that yields a `Session`. FastAPI uses it with `Depends(get_session)` so each HTTP request gets its own database session.

## Tables / models

Each `SQLModel, table=True` class in `backend/anvaya/models/` becomes a table:

| Model / Table | Purpose |
|---|---|
| `Incident` (`incidents`) | The main incident with status and self-correction state |
| `TelemetryEvent` (`telemetry_events`) | Synthetic security events (login, process, network, etc.) |
| `DetectionRule` (`detection_rules`) | Rules proposed by the self-correction engine |
| `RuleCondition` (`rule_conditions`) | Individual conditions inside a rule |
| `DetectionRun` (`detection_runs`) | A run of the ML detector |
| `DetectionResult` (`detection_results`) | Per-event detection results |
| `ReplayRun` (`replay_runs`) | Pre/post-patch replay record |
| `AuditRecord` (`audit_records`) | Hash-linked audit trail |
| `Asset` (`assets`) | Network assets (hosts, services, users) |
| `AssetRelationship` (`asset_relationships`) | Connections between assets |
| `GraphNode` (`graph_nodes`) | Nodes of a BlastScope graph |
| `GraphEdge` (`graph_edges`) | Edges of a BlastScope graph |
| `BlastRadiusResult` (`blast_radius_results`) | Blast-radius score and paths |
| `CounterfactualAnalysis` (`counterfactual_analyses`) | What-If analysis records |
| `Simulation` / `SimulationStep` (`simulations`) | Ecosystem simulation data |
| `ModelVersion` (`model_versions`) | Trained ML model metadata and artifact hash |
| `DatasetVersion` (`dataset_versions`) | Dataset metadata and split sizes |

## PostgreSQL terms

- **Table** — a named collection of rows, like a spreadsheet page.
- **Row / record** — one entry in a table.
- **Column / field** — one property of every row.
- **Primary key** — a unique ID for a row (usually `id`).
- **Foreign key** — a column that points to a row in another table.
- **Index** — a data structure that speeds up lookups.
- **Transaction** — a group of database operations that succeed or fail together.
- **SQLAlchemy** — the Python database toolkit underneath SQLModel.
- **ORM** — Object-Relational Mapper; lets you use Python classes instead of raw SQL.

## How migrations work

Currently SQLModel creates tables automatically on startup (`SQLModel.metadata.create_all`). For a production system you would normally use **Alembic** migration scripts. Alembic is listed in `pyproject.toml` as a dependency so the project is migration-ready, but no migration files are shipped yet.

## Integrity

The audit table uses hash-linking. Each `AuditRecord` stores a `record_hash` that depends on the previous record's hash, forming a chain. The `verify_chain()` function in `backend/anvaya/models/audit.py` checks that the chain has not been broken.
