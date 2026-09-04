# 14 — File Inventory

This file maps every important project file to its job. It is grouped by concern so a judge can find the source of any feature.

## How to see the full live tree

Run this from the project root to see all non-generated files:

```bash
find . -not -path '*/\.git/*' \
       -not -path '*/\.venv/*' \
       -not -path '*/node_modules/*' \
       -not -path '*/.next/*' \
       -not -path '*/__pycache__/*' \
       -not -path '*/.pytest_cache/*' \
       -not -path '*/.mypy_cache/*' \
       -not -path '*/.ruff_cache/*' \
       -not -path '*/.egg-info/*' \
       -not -path '*/ml/artifacts/*' \
       -type f | sort
```

## Project root and config

| File | Purpose |
|---|---|
| `README.md` | High-level overview, install, and quick start |
| `AGENTS.md` | Devin engineering charter and autonomy rules |
| `pyproject.toml` | Python package, dependencies, tool config (ruff, mypy, pytest) |
| `docker-compose.yml` | Spin up backend, frontend, and PostgreSQL locally |
| `Dockerfile.backend` | Container image for the FastAPI server |
| `Dockerfile.frontend` | Container image for the Next.js app |
| `railway.toml` | Railway.app backend deployment config |
| `fly.toml` | Fly.io backend deployment config |
| `.env` / `.env.example` | Local environment variables (database, OpenAI, ports) |

## Documentation

| File | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | System topology and stack |
| `docs/API_CONTRACT.md` | HTTP contract between frontend and backend |
| `docs/PROJECT_STATUS.md` | Build phase checklist and evidence |
| `docs/JUDGE_PROOF.md` | Observable miss → catch demo steps |
| `docs/SECURITY_AUDIT.md` | Defensive scope and security notes |
| `docs/ASSUMPTIONS.md` | Engineering decisions and assumptions |
| `docs/DECISIONS.md` | Design decision log |
| `docs/REQUIREMENTS_TRACEABILITY.md` | Requirements mapping |
| `docs/ui/ANVAYA_UI_SOURCE_OF_TRUTH.md` | Exact UI reference specification |
| `docs/BOOTSTRAP_PROMPT.md` | Master Devin backend prompt |
| `docs/BOOTSTRAP_UI_PROMPT.md` | Master Devin UI prompt |
| `.devin/rules/*.md` | Per-topic agent rules (autonomy, data, LLM, security, UI, etc.) |
| `.devin/workflow/*.md` | Build and UI execution workflows |
| `.devin/references/ui/*.png` | Nine UI reference screenshots used as visual source of truth |

## This guide

| File | Purpose |
|---|---|
| `guide/README.md` | Master index and quick commands |
| `guide/01-what-is-anvaya.md` | Product pitch and problem/solution |
| `guide/02-architecture.md` | System layers and data flow |
| `guide/03-frontend-nextjs.md` | Next.js, routing, React Query, components |
| `guide/04-backend-fastapi.md` | FastAPI, routers, endpoints, config |
| `guide/05-database-postgres.md` | SQLModel, tables, PostgreSQL |
| `guide/06-ml-pipeline.md` | Isolation Forest, Logistic Regression, features |
| `guide/07-engines.md` | Sentinel, BlastScope, What-If, ControlLedger |
| `guide/08-simulator.md` | Synthetic telemetry and scenarios |
| `guide/09-lifecycle.md` | Incident and self-correction lifecycles |
| `guide/10-api-contract.md` | REST endpoint table and error handling |
| `guide/11-testing.md` | Test suite and commands |
| `guide/12-deployment.md` | Docker, Vercel, Railway, Fly.io |
| `guide/13-tech-concepts-glossary.md` | Plain-English glossary |
| `guide/14-file-inventory.md` | This file |

## Backend (`backend/anvaya/`)

| File | Purpose |
|---|---|
| `main.py` | FastAPI app creation, lifespan, middleware, router registration |
| `config.py` | `Settings` class loading env vars and `.env` |
| `db.py` | SQLModel engine, `init_db()`, session generator |
| `logging.py` | `structlog` JSON logging setup |
| `cli.py` | CLI commands: `serve`, `demo`, `init-db` |
| `__init__.py` | Package marker |

### Models (`backend/anvaya/models/`)

| File | Purpose |
|---|---|
| `__init__.py` | Exports all models |
| `enums.py` | Enum values: `IncidentStatus`, `SelfCorrectionStatus`, `RuleStatus`, etc. |
| `incident.py` | `Incident` table and lifecycle/self-correction state machines |
| `telemetry.py` | `TelemetryEvent` and `TelemetryEventType` |
| `rule.py` | `DetectionRule`, `RuleCondition`, `RuleGroup` |
| `detection.py` | `DetectionRun`, `DetectionResult` |
| `replay.py` | `ReplayRun`, `ReplayStatus` |
| `audit.py` | `AuditRecord` and `verify_chain()` hash-chain logic |
| `asset.py` | `Asset`, `AssetRelationship`, `AssetType` |
| `graph.py` | `GraphNode`, `GraphEdge`, `BlastRadiusResult` |
| `counterfactual.py` | `CounterfactualAnalysis` |
| `simulation.py` | `Simulation`, `SimulationStep` |
| `model_version.py` | `ModelVersion` |
| `dataset.py` | `DatasetVersion` |

### Routers (`backend/anvaya/routers/`)

| File | Purpose |
|---|---|
| `incidents.py` | Incident CRUD and transitions |
| `telemetry.py` | Telemetry ingestion and queries |
| `detections.py` | ML detection runs |
| `rules.py` | Detection rule API |
| `replay.py` | Replay run records |
| `sentinel.py` | Self-correction API (backtrack, propose, validate, replay, full cycle) |
| `blastscope.py` | Blast-radius API and gallery |
| `whatif.py` | Counterfactual analysis API |
| `audit.py` | Audit records and chain verification |
| `graph.py` | Graph nodes/edges, segments, reachability |
| `metrics.py` | Dashboard metrics, engine consensus, trophies |
| `models.py` | ML model versions API |
| `datasets.py` | Dataset generation API |
| `simulation.py` | Ecosystem simulation API |
| `demo.py` | One-shot full demo endpoint |
| `__init__.py` | Empty package marker |

### Engines (`backend/anvaya/`)

| File | Purpose |
|---|---|
| `sentinel/__init__.py` | SentinelBacktracker: backtrack, propose, validate, replay |
| `sentinel/engine.py` | (companion engine file) |
| `blastscope/__init__.py` | BlastScope: NetworkX graph and blast radius |
| `blastscope/engine.py` | (companion engine file) |
| `whatif/__init__.py` | What-If: Logistic Regression counterfactuals |
| `whatif/engine.py` | (companion engine file) |
| `llm/__init__.py` | LLM helpers and prompt handling |
| `data/factory.py` | Data factory orchestration |
| `data/__init__.py` | Package marker |
| `demo/orchestrator.py` | End-to-end demo orchestrator |

## ML (`ml/anvaya/`)

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `alertness/__init__.py` | `AlertnessEngine` Isolation Forest train/predict/persist |
| `features.py` | Feature extraction from telemetry events, feature column list |
| `ml/artifacts/*.joblib` | Generated trained model and scaler files (not hand-edited) |

## Simulator (`simulator/anvaya/`)

| File | Purpose |
|---|---|
| `__init__.py` | Package marker |
| `scenarios.py` | `ScenarioTemplate` catalog: normal, suspicious, attack, self-correction |
| `generator.py` | `TelemetryGenerator` deterministic event generator and dataset splits |

## Frontend (`frontend/`)

| File | Purpose |
|---|---|
| `package.json` | Node dependencies and scripts |
| `next.config.ts` | Next.js configuration (unoptimized images) |
| `tsconfig.json` | TypeScript config |
| `postcss.config.mjs` | PostCSS / Tailwind setup |
| `eslint.config.mjs` | ESLint configuration |
| `globals.css` | Global CSS and custom properties (dark theme) |
| `vercel.json` | Vercel deployment config |

### App pages (`frontend/app/`)

| File | Route | Purpose |
|---|---|---|
| `layout.tsx` | all | Root layout, fonts, dark mode, providers |
| `page.tsx` | `/` | Arbor / landing |
| `overview/page.tsx` | `/overview` | Live SOC overview |
| `incidents/page.tsx` | `/incidents` | Incident list and detail |
| `impact-gallery/page.tsx` | `/impact-gallery` | Impact cards |
| `reach-board/page.tsx` | `/reach-board` | Reachability board |
| `miss-replay/page.tsx` | `/miss-replay` | Miss → replay view |
| `threat-ecosystem/page.tsx` | `/threat-ecosystem` | Ecosystem sim |
| `nerve-arena/page.tsx` | `/nerve-arena` | Engine consensus |
| `risk-orbits/page.tsx` | `/risk-orbits` | Risk visualisation |
| `segments/page.tsx` | `/segments` | Network segments |
| `trophy-wall/page.tsx` | `/trophy-wall` | Sealed trophies |
| `ledger/page.tsx` | `/ledger` | Audit ledger |
| `settings/page.tsx` | `/settings` | Settings and status |

### Components (`frontend/components/`)

| File | Purpose |
|---|---|
| `providers.tsx` | React Query + global store + sidebar providers |
| `app-shell.tsx` | Common page shell (top bar, title, children) |
| `sidebar.tsx` | Main navigation, projects, sessions, notifications |
| `top-bar.tsx` | Header with clock, status, ecosystem controls |
| `primitives.tsx` | Reusable UI: Panel, Chip, Bar, Dot, Mono, etc. |
| `graph-canvas.tsx` | Network graph renderer |
| `create-project-dialog.tsx` | New incident / project dialog |
| `demo-button.tsx` | One-click demo button |
| `group-by.tsx` | Incident grouping menu |

### Lib (`frontend/lib/`)

| File | Purpose |
|---|---|
| `api.ts` | HTTP client, `AnvayaAPI`, all React Query hooks |
| `store.tsx` | Global client state (Zustand-like) |
| `incidents.ts` | Incident grouping and navigation helpers |
| `data.ts` | Static and helper data |
| `graph.tsx` | Graph rendering helpers |
| `hooks.ts` | Custom React hooks |
| `utils.ts` | Utility functions (cn, etc.) |

## Tests (`tests/`)

| File | Purpose |
|---|---|
| `conftest.py` | Shared pytest fixtures |
| `test_api.py` | FastAPI endpoint tests |
| `test_audit.py` | Audit chain integrity tests |
| `test_blastscope.py` | BlastScope graph tests |
| `test_data_factory.py` | Synthetic data tests |
| `test_features.py` | Feature extraction tests |
| `test_incident.py` | Incident state machine tests |
| `test_self_correction.py` | Full self-correction loop test |

## GitHub / CI

| File | Purpose |
|---|---|
| `.github/workflows/devin-ci-fix.yml` | CI workflow for automated checks |

## Generated / ignored files

| Pattern | What it is |
|---|---|
| `frontend/node_modules/` | Downloaded npm packages (do not commit) |
| `frontend/.next/` | Next.js build output (do not commit) |
| `backend/.venv/` | Python virtual environment (do not commit) |
| `**/__pycache__/` | Compiled Python bytecode (do not commit) |
| `ml/artifacts/*.joblib` | Trained ML model binaries (generated) |
| `anvaya.db`, `backend/anvaya.db` | Local SQLite databases (generated) |
