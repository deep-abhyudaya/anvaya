# 02 — Architecture

## System topology

The system has three main layers. The frontend talks to the backend over a REST API. The backend talks to a PostgreSQL database and runs five special-purpose engines. All engines share the same data store.

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Next.js 15)                     │
│  App Router · TypeScript · Tailwind CSS · shadcn/ui           │
│  React Query (3-5 s polling) · Recharts · Cytoscape/React Flow│
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API (JSON)
┌──────────────────────────┴──────────────────────────────────┐
│                    Backend (FastAPI)                          │
│  Pydantic · SQLModel · structured logging · Uvicorn           │
│  Routers: incidents, telemetry, detections, rules, replay,    │
│  sentinel, blastscope, whatif, audit, graph, metrics, ...     │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │
┌──────┴───┐ ┌───┴────┐ ┌───┴────┐ ┌───┴────┐ ┌───┴────┐
│ Alertness│ │Synthetic│ │Sentinel│ │BlastScope│ │What-If │
│Isolation │ │Scenario │ │Backtrack│ │NetworkX │ │Logistic│
│Forest    │ │Generator│ │Engine  │ │Graph    │ │Regress.│
└──────────┘ └────────┘ └────────┘ └────────┘ └────────┘
       │
┌──────┴───────────────────────────────────────────────────────┐
│              PostgreSQL (SQLModel / SQLAlchemy)               │
│  incidents · telemetry · rules · detections · replays ·      │
│  audit_records · graph_nodes · graph_edges · assets · models │
└──────────────────────────────────────────────────────────────┘
```

## Technology stack

| Layer | Technology | Why it was chosen |
|---|---|---|
| Frontend | Next.js 15, App Router, TypeScript, Tailwind CSS v4 | Modern React framework with file-based routing and fast styling |
| Data fetching | React Query (`@tanstack/react-query`) | Automatic background polling, caching, and refetching every 3–5 seconds |
| Visualisation | Recharts, Cytoscape.js / React Flow | Charts and network graphs for the dashboard |
| Backend | FastAPI, Uvicorn, Pydantic, SQLModel | Fast Python API with automatic validation and OpenAPI docs |
| Database | PostgreSQL 15+ (or SQLite for local dev) | Reliable, production-grade relational database |
| ML | scikit-learn (Isolation Forest, Logistic Regression) | Battle-tested, no GPU needed, easy to explain |
| Graph | NetworkX | Standard Python graph library for reachability and paths |
| LLM | OpenAI GPT-4o mini via function calling / JSON mode | Generates rule names and descriptions; falls back to deterministic text if no key |
| Testing | pytest, pytest-asyncio | Unit, integration, and API tests |
| Deployment | Vercel (frontend), Railway / Fly.io (backend), Docker | Cloud-native deployment configs included |

## Core data flow

A demo run looks like this:

1. `TelemetryGenerator` builds a seeded, synthetic event stream.
2. `AlertnessEngine` (Isolation Forest) runs a pre-patch detection. It misses `ATK-MISS-001`.
3. `SentinelBacktracker` confirms the miss, backtracks, proposes a rule, validates it, and replays the attack.
4. The replay proves the attack is now caught.
5. `BlastScopeEngine` builds a NetworkX graph from assets and computes a blast radius.
6. `WhatIfEngine` runs a Logistic Regression counterfactual to show how risk would change.
7. The incident is transitioned to `SEALED`.
8. `ControlLedger` writes hash-linked audit records.

## Design principles

- **Deterministic**: synthetic data uses a fixed seed so the same demo produces the same numbers.
- **Typed**: Pydantic and SQLModel give every request and database row a strict schema.
- **Tested**: 49 tests cover state machines, audit integrity, ML, and the API.
- **Observable**: the whole lifecycle can be run from one CLI command and inspected in the dashboard.
