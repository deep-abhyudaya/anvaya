# ANVAYA — Requirements Traceability

| Requirement | Source | Implementation | Verification |
|---|---|---|---|
| Unified lifecycle: detected→analyzed→simulated→explained→sealed | AGENTS.md, Spec | `backend/anvaya/models/incident.py` state machine | Unit tests for valid/invalid transitions |
| Alertness: Isolation Forest | AGENTS.md | `ml/anvaya/alertness/` | Evaluation report, inference tests |
| Self-Enhancement: SentinelBacktracker | AGENTS.md | `backend/anvaya/sentinel/` | E2E demo test: miss→patch→replay→caught |
| Counter-Attack: BlastScope (NetworkX) | AGENTS.md | `backend/anvaya/blastscope/` | Graph traversal tests |
| Defense: What-If (Logistic Regression) | AGENTS.md | `ml/anvaya/whatif/` | Counterfactual tests |
| ControlLedger: audit chain | AGENTS.md | `backend/anvaya/audit/` | Tamper detection test |
| Next.js 15 dashboard | AGENTS.md | `frontend/` | Build + screenshot QA |
| FastAPI backend | AGENTS.md | `backend/` | API tests |
| PostgreSQL + SQLModel | AGENTS.md | `backend/anvaya/db.py` | Migration tests |
| GPT-4o mini function calling | AGENTS.md | `backend/anvaya/llm/` | Schema validation tests |
| React Query polling 3-5s | AGENTS.md | `frontend/src/hooks/` | Component tests |
| Synthetic data factory | DATA_FACTORY.md | `simulator/anvaya/` | Dataset validation tests |
| Deterministic replay | SELF_CORRECTION.md | `backend/anvaya/replay/` | Replay identity tests |
| 9 UI pages matching references | UI_EXACT_BUILD.md | `frontend/src/app/` | Screenshot comparison |
| `anvaya demo` command | MASTER_BUILD.md | `backend/anvaya/cli.py` | E2E demo test |
| No fake metrics/results | AGENTS.md | All layers | Judge-mode verification |
