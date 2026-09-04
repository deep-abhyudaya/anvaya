# ANVAYA — Technical Decisions

## D-001: Monorepo with shared Python package
The backend, ML, and simulator share a single Python package `anvaya` installed in editable mode. This avoids code duplication for models, schemas, and utilities.

## D-002: SQLModel for ORM
SQLModel combines Pydantic validation with SQLAlchemy ORM, matching the spec requirement and reducing schema duplication between API schemas and database models.

## D-003: Alembic for migrations
Alembic provides migration versioning. Migrations are auto-generated from SQLModel metadata.

## D-004: Rule DSL as structured JSON
Detection rules are JSON objects with a restricted condition grammar: `{field, operator, value}` tuples combined with AND/OR. Evaluated by a safe interpreter — no `eval()` or `exec()`.

## D-005: Scenario-based telemetry generation
Each synthetic scenario is a declarative template with entities, timeline, ground truth, and expected detection behavior. Scenarios are versioned and seeded.

## D-006: Feature extraction as deterministic pipeline
Feature extraction transforms telemetry events into numeric vectors using a fixed schema. The pipeline is fit on training data only and persisted with the model.

## D-007: LLM fallback for local dev
When no API key is present, a deterministic template-based rule proposer generates candidate rules from evidence patterns. This ensures the self-correction loop works without external dependencies.

## D-008: Cytoscape.js for graph-heavy views
NERVE ARBOR and THREAT ECOSYSTEM use Cytoscape.js for force-directed layouts with custom node/edge styling. React Flow is used for the replay timeline flow diagram.

## D-009: Docker Compose for local PostgreSQL
Docker Compose provides PostgreSQL + pgAdmin for local development. The app also supports SQLite for quick testing.

## D-010: CLI via Typer
The `anvaya` CLI is built with Typer for subcommands: `demo`, `data generate`, `data validate`, `data summarize`, `train`, `evaluate`.

## D-011: Live execution context and reasoning loop
The agentic layer keeps a live `ExecutionContext` SQLModel table separate from the immutable `Execution` and `ExecutionEvent` tables. This preserves existing schemas while storing the mutable plan, observations, messages, reasoning summary, and current action. `AgentLoop` is the core runner, `ReasoningGenerator` produces user-safe summaries (with optional model streaming), and `POST /agent/execute` supports `?background=true` for interactive use. User messages and cancellations are processed at step boundaries.
