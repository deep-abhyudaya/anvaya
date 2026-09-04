# ANVAYA — Feature Traces

## Feature: Live detection from a telemetry POST

### User intent
Send a telemetry event and have ANVAYA detect an anomaly, create an incident, and notify downstream integrations.

### Entry
- `POST /telemetry` (frontend or external) or `anvaya watch`.

### Backend
- `backend/anvaya/routers/telemetry.py` `create_telemetry`
- `backend/anvaya/live/__init__.py` `score_and_maybe_flag`

### Logic
1. Persist `TelemetryEvent`.
2. Load latest `AlertnessEngine`.
3. `predict_single(event)`.
4. If detected:
   - create/link `Incident`
   - append `AuditRecord`
   - `on_incident_event(DETECTED, ...)`

### AI
- `AlertnessEngine` Isolation Forest scoring.

### Data
- `TelemetryEvent`, `Incident`, `AuditRecord`, `ModelVersion`.

### Side effects
- New incident row.
- Audit record.
- Tavily/n8n/Signal/Gmail dispatch.

### Response
```json
{"event": {...}, "detection": {"scored": true, "detected": true, "incident_id": "..."}}
```

### UI
- Incident appears in `/sentinel#incidents` via React Query polling.
- Evidence summary updated if Tavily used.

### Failure
- No model trained → `scored: False`.
- `predict_single` exception → `scored: False` with reason.

### Source map
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/routers/telemetry.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/live/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/ml/anvaya/alertness/__init__.py" />

---

## Feature: Agent investigates a missed attack

### User intent
Ask ANVAYA to investigate an incident and produce a replay, blast scope, what-if, and sealed audit.

### Entry
- Frontend agent console `AnvayaAPI.agentExecute` or CLI `/investigate`.

### Frontend
- `components/agent/agent-context.tsx` `start`.
- `components/agent/agent-console.tsx` renders tool cards.
- `lib/api.ts` `agentExecute`.

### Backend
- `routers/agent.py` `POST /agent/execute`.
- `AgentOrchestrator.start` → `run`.
- `AgentLoop.run_investigation`.
- `LocalToolExecutor.execute` dispatches each tool.

### Logic
Plan typically includes:
1. `get_incident`
2. `get_telemetry`
3. `run_sentinel_trace`
4. `confirm_ground_truth`
5. `propose_rule`
6. `validate_rule`
7. `run_replay`
8. `run_blastscope`
9. `run_what_if`
10. `append_audit_record`
11. `verify_audit_chain`
12. `seal_incident`

### AI
- `ModelPlanner` if external LLM configured; otherwise `DeterministicPlanner`.
- `ReasoningGenerator` produces safe reasoning text.

### Data
- `Execution`, `ExecutionContext`, `ExecutionEvent`, `Incident`, `DetectionRule`, `ReplayRun`, `BlastRadiusResult`, `CounterfactualAnalysis`, `AuditRecord`.

### Side effects
- Incident status advanced.
- Rule proposed/validated.
- Replay run created.
- Blast/what-if persisted.
- Audit chain extended.
- n8n/Signal/Gmail dispatch on `SEALED`.

### Response
Execution summary with `execution_id`; events streamed via SSE/polling.

### UI
- Agent console shows `agent.started`, `tool.started`, `tool.completed`, `artifact.created`.
- Clickable artifact links to `/miss-replay`, `/risk-orbits`, etc.

### Failure
- Step failure with `stop_on_failure=True` aborts execution.
- Fallback used if provider unavailable.
- Tool not found → `ToolResult` with `error_code: tool_not_found`.

### Source map
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/frontend/lib/api.ts" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/routers/agent.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/orchestrator.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/agent_loop.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/executor.py" />

---

## Feature: Project artifact build

### User intent
Generate all project artifacts (orbits, incidents, ecosystem, etc.) from a dataset.

### Entry
- `POST /projects/{id}/build` or `/agent/execute "generate all"`.

### Frontend
- `app/projects/[projectId]/page.tsx` generate button.
- `components/build/build-panel.tsx`.

### Backend
- `routers/projects.py` `build_project` or `AgentOrchestrator.run` → `LocalToolExecutor.handle_manage_artifacts`.

### Logic
1. Resolve project and dataset.
2. For each artifact type, create `Generation`.
3. `ArtifactBuilder.run` loads manifest.
4. Each manifest step emits `artifact.*` events.
5. `ArtifactGenerator` builds `WorldModel` and creates payloads.
6. Persist `ProjectArtifact` + `ProjectArtifactPayload`.

### Side effects
- `ProjectArtifactPayload` rows.
- `Generation` status updated.
- Event stream.

### Response
`{generation_id, generation_ids, execution_id, target, targets, status}`.

Single-target requests keep the original shape (`targets` mirrors `target`).
Multi-target requests (`targets`/`requested_artifacts` list) mint ONE
execution and run the builders sequentially under it via
`build_artifacts`, so the agent panel shows one continuous narration
stream across all requested artifacts, finalized by `agent.completed`.

### UI
- Build panel renders step-by-step progress.
- Tiles use `useArtifactSource` (now taking a required `artifactType`) to
  show live or final payload; `isBuilding` is scoped to the artifact type
  whose build is currently active (`activeBuildTarget` via
  `build.currentIndex` → item `targetArtifactType`), so generating one
  artifact no longer flips every other page into its build shell.
- Project page "Generate" calls `createBuildSession` with the selected
  targets, then `useAgent().attachExecution(execution_id)` subscribes the
  panel to that execution's SSE stream and opens it.

### Failure
- `ArtifactBuilder` retries failed steps.
- `stop_on_failure` can abort.

### Source map
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/generation.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/generations/builder.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/generations/manifests.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/project.py" />

---

## Feature: Train models and run self-correction

### User intent
Generate a dataset, train Alertness and What-If, and prove the miss→catch cycle.

### Entry
- CLI `anvaya train` or interactive `/train`.

### Backend
- `cli/typer_app.py` `train`.
- `cli/shell.py` `_do_train`.

### Logic
1. `DataFactory.generate(config)` creates `TelemetryEvent` + `DatasetVersion` and exports CSV.
2. `AlertnessEngine.train` on events.
3. `WhatIfEngine.train` on events.
4. `SentinelEngine.run_full_cycle` on the ATK-MISS-001 self-correction scenario.

### Data
- `DatasetVersion`, `TelemetryEvent`, `ModelVersion`, `Incident`, `DetectionRule`, `ReplayRun`, `AuditRecord`.

### Side effects
- `ml/artifacts/*.joblib` files.
- `datasets/*.csv`.
- New incident and rule.

### Response
Training summary with metrics.

### UI
- Models appear in `/settings` or model selector.
- Incident from training visible in dashboard.

### Failure
- No attack events → Sentinel cannot backtrack.
- Model training exception → fallback or error.

### Source map
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/cli/typer_app.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/cli/shell.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/data/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/ml/anvaya/alertness/__init__.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/sentinel/__init__.py" />
