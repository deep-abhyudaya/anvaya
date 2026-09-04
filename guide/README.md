# ANVAYA Hackathon Judge Guide — Master Index

Welcome. This `guide/` folder contains a complete, plain-English walkthrough of the ANVAYA autonomous cyber SOC project. It is written for hackathon judges, teammates, and anyone who needs to understand the architecture, the code, and the science behind the system quickly.

## What is ANVAYA?

ANVAYA is an autonomous Security Operations Centre (SOC) simulator. It generates synthetic cyber-attack telemetry, tries to detect it with machine learning, learns from missed attacks, proposes and validates new detection rules, replays the same attack to prove it now catches it, simulates how far the attack could spread, asks "what if we changed this?" to reduce risk, and finally seals the whole investigation into a tamper-evident audit chain.

## What these guides cover

| # | File | Purpose |
|---|---|---|
| 1 | [01-what-is-anvaya.md](01-what-is-anvaya.md) | Elevator pitch, key selling points, and the problem it solves |
| 2 | [02-architecture.md](02-architecture.md) | System topology, layers, tech stack, data flow |
| 3 | [03-frontend-nextjs.md](03-frontend-nextjs.md) | Next.js 15, App Router, dynamic routing, React Query, UI pages |
| 4 | [04-backend-fastapi.md](04-backend-fastapi.md) | FastAPI, routers, Pydantic, lifespan, security, CLI |
| 5 | [05-database-postgres.md](05-database-postgres.md) | PostgreSQL, SQLModel, tables, and how data is stored |
| 6 | [06-ml-pipeline.md](06-ml-pipeline.md) | Isolation Forest, Logistic Regression, feature extraction, training |
| 7 | [07-engines.md](07-engines.md) | SentinelBacktracker, BlastScope, What-If, ControlLedger |
| 8 | [08-simulator.md](08-simulator.md) | Synthetic data factory, scenarios, telemetry generator |
| 9 | [09-lifecycle.md](09-lifecycle.md) | The incident and self-correction lifecycles |
| 10 | [10-api-contract.md](10-api-contract.md) | REST endpoints and how the frontend talks to the backend |
| 11 | [11-testing.md](11-testing.md) | Test suite, what is checked, how to run it |
| 12 | [12-deployment.md](12-deployment.md) | Vercel, Railway, Fly.io, Docker, quick start |
| 13 | [13-tech-concepts-glossary.md](13-tech-concepts-glossary.md) | Simple definitions of every tech term used |
| 14 | [14-file-inventory.md](14-file-inventory.md) | Every project file and its job |

## Quick commands for judges

```bash
# Install backend
pip install -e ".[dev]"

# Run backend
anvaya serve

# Run the full judge-proof demo
anvaya demo

# Run tests
python -m pytest tests/ -v

# Install and run frontend
cd frontend
npm install
npm run dev
```

Dashboard: `http://localhost:3000`  
API: `http://localhost:8000`  
Auto-generated API docs: `http://localhost:8000/docs`

## The one-sentence proof

> ANVAYA can take a missed cyber attack, invent a rule that would have caught it, replay the exact same attack, prove it is now caught, show how far it could have spread, suggest a safer counterfactual, and lock the whole story into an unchangeable audit record.
