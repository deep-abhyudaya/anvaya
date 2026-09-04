# ANVAYA — Architecture

## Overview
ANVAYA is an autonomous cyber SOC platform with a self-correction loop at its core. It detects, analyzes, simulates, explains, and seals security incidents using ML-driven anomaly detection, graph-based blast-radius simulation, counterfactual risk analysis, and tamper-evident audit trails.

## System Topology

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 15)                     │
│  App Router · TypeScript · Tailwind · React Query (3-5s poll) │
│  Cytoscape.js / React Flow · Recharts                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API
┌──────────────────────────┴──────────────────────────────────┐
│                    Backend (FastAPI)                          │
│  Pydantic schemas · SQLModel · structured logging            │
│  Domain routers: incidents, telemetry, detections, rules,    │
│  replay, sentinel, blastscope, whatif, audit, graph,         │
│  metrics, models, datasets, demo, agent                      │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │
┌──────┴───┐ ┌───┴────┐ ┌───┴────┐ ┌───┴────┐ ┌───┴────┐
│ ML Engine│ │Simulator│ │Sentinel│ │BlastScope│ │What-If │
│Isolation │ │Telemetry│ │Backtrack│ │NetworkX │ │Logistic│
│Forest    │ │Generator│ │Engine  │ │Graph    │ │Regress.│
└──────────┘ └────────┘ └────────┘ └────────┘ └────────┘
       │
┌──────┴───────────────────────────────────────────────────────┐
│              PostgreSQL (SQLModel / SQLAlchemy)               │
│  incidents · telemetry · rules · detections · replays ·      │
│  audit_records · graph_nodes · graph_edges · models ·        │
│  simulations · counterfactuals · assets · datasets           │
└──────────────────────────────────────────────────────────────┘
```

## Incident Lifecycle

### Unified lifecycle
`detected → analyzed → simulated → explained → sealed`

### Self-correction lifecycle
`MISS → GROUND_TRUTH_CONFIRMED → BACKTRACKING → EVIDENCE_IDENTIFIED → RULE_PROPOSED → RULE_VALIDATED → REPLAYING → CAUGHT / STILL_MISSED`

## Core Subsystems

### 1. Alertness Engine (ML)
- Isolation Forest for behavioral anomaly detection
- Feature extraction from telemetry events
- Deterministic preprocessing pipeline
- Model versioning and artifact persistence
- Threshold-based detection with configurable sensitivity

### 2. SentinelBacktracker (Self-Correction)
- Confirmed miss ingestion
- Historical telemetry backtracking
- Evidence timeline reconstruction
- Candidate rule proposal (LLM-assisted, deterministically validated)
- Identical attack replay with pre/post-patch comparison
- Outcome persistence and audit

### 3. BlastScope (Counter-Attack)
- NetworkX graph construction from asset relationships
- Reachability and blast-radius traversal
- Impact scoring based on critical asset exposure
- Observed vs simulated vs possible distinction

### 4. What-If Watcher (Defense)
- Logistic Regression risk model
- Counterfactual analysis with controlled feature changes
- Risk delta computation
- Model-based (not causal) explanations

### 5. ControlLedger (Audit)
- Append-only audit chain with hash linking
- Compliance-mapped control records
- Tamper detection via chain verification
- Every state transition produces an audit record

### 6. Synthetic Data Factory
- Deterministic seeded telemetry generation
- Normal, suspicious, and attack scenario templates
- Ground-truth labels with replay identifiers
- Train/validation/test split with anti-leakage guarantees

### 7. Agentic Execution Layer
- Provider-neutral `ToolRegistry` with schema-validated inputs
- `LocalToolExecutor` wrapping existing ANVAYA engines
- Deterministic `AgentOrchestrator` that plans and runs the full self-correction lifecycle
- `AgentProfile` and `ModelConfig` for provider-neutral profile/model selection
- `MessageGenerator` emits operational `agent.message` events before/after every tool
- `ExecutionEvent` stream (`agent.started`, `tool.started`, `artifact.created`, `agent.completed`, etc.)
- Optional external provider adapters with truthful availability and local fallbacks (OpenAI, Tavily, n8n, Lyzr, Swytchcode)
- Persistent right-side Agent Console in the Next.js shell with live event stream, tool cards, artifact links, profile/model selectors, and SSE support

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, App Router, TypeScript, Tailwind CSS, shadcn/ui |
| Visualization | Cytoscape.js, React Flow, Recharts |
| Data fetching | React Query (polling 3-5s) |
| Backend | FastAPI, Python 3.11+, Pydantic, SQLModel |
| Database | PostgreSQL 15+ |
| ML | scikit-learn, Isolation Forest, Logistic Regression |
| Graph | NetworkX |
| LLM | GPT-4o mini via function calling (structured outputs) |
| Testing | pytest, pytest-asyncio, Vitest/Playwright |
| Deployment | Vercel (frontend), Railway/Fly.io (backend) |

## API Design

Domain-oriented routers:
- `/api/v1/incidents` — CRUD, state transitions, lifecycle
- `/api/v1/telemetry` — event ingestion, querying
- `/api/v1/detections` — detection runs, results
- `/api/v1/rules` — versioned detection rules
- `/api/v1/replay` — replay execution and results
- `/api/v1/sentinel` — backtracking, rule proposal, validation
- `/api/v1/blastscope` — graph construction, traversal, impact
- `/api/v1/whatif` — counterfactual analysis
- `/api/v1/audit` — audit chain, verification
- `/api/v1/graph` — graph nodes/edges for visualization
- `/api/v1/metrics` — dashboard aggregate metrics
- `/api/v1/models` — model versions, status
- `/api/v1/datasets` — generation, validation, metadata
- `/api/v1/demo` — orchestration endpoint
- `/api/v1/agent` — agentic execution, tool registry, live event trace

## Data Flow (Self-Correction Demo)

```
1. Generate telemetry (normal + attack scenario)
2. Run pre-patch detection → MISS
3. Confirm ground truth (attack was real)
4. Backtrack telemetry evidence window
5. Propose candidate detection rule (LLM + deterministic validation)
6. Validate rule against historical data
7. Replay identical attack with patched rule
8. Post-patch detection → CAUGHT
9. Run BlastScope on compromised assets
10. Run What-If counterfactual analysis
11. Seal incident → audit chain record
12. Verify audit integrity
```

## Dataset-Grounded Artifact World

A new data-driven artifact layer sits between uploaded datasets and the dashboard:

- `dataset_profile.py` builds a `DatasetProfile` that profiles column types, maps canonical fields (timestamp, source_ip, destination_ip, host, user, etc.), and reports data quality metrics.
- `world.py` builds a deterministic `WorldModel` from the profiled dataset. It extracts entities, telemetry events, incidents, attack families, blast-radius orbits, network segments, reachability maps, trophy entries, an ecosystem graph, a nerve-arena consensus, a replay timeline, and a control ledger.
- `generation.py` persists each part of the `WorldModel` as `ProjectArtifact` + `ProjectArtifactPayload` rows, tagged with a dataset/generation fingerprint and provenance.
- `agent/executor.py` exposes `manage_artifacts` to generate, regenerate, and delete these artifacts, emitting lifecycle `ExecutionEvent`s (`artifact.world_build_started`, `artifact.generating`, `artifact.saved`, `artifact.deleted`, etc.).
- `routers/projects.py` adds `/projects/{id}/{type}/latest`, `/projects/{id}/{type}/regenerate`, `/projects/{id}/{type}/inspect`, and delete endpoints for every artifact type.
- The frontend uses `useProjectArtifactLatest` to pull real artifact payloads into Risk Orbits, Nerve Arena, Threat Ecosystem, Reach Board, and Segments, replacing the previous fully-static demo datasets.
