# ANVAYA Judge-Observable Proof

## Final principle

The judge can verify the complete self-correction cycle by running:

```bash
anvaya demo
```

This produces observable, verifiable output at each stage:

### 1. MISS (Pre-patch detection fails)
- Telemetry generated from `ATK-MISS-001` scenario (deterministic seed)
- Isolation Forest detector runs on events
- Attack events are NOT flagged (score above threshold)
- Ground truth labels confirm attack was present but missed

### 2. GROUND_TRUTH_CONFIRMED
- Scenario template provides ground truth labels
- SentinelBacktracker identifies the missed attack pattern
- Incident created with `self_correction_status = GROUND_TRUTH_CONFIRMED`

### 3. BACKTRACKING → EVIDENCE_IDENTIFIED
- Backtracker analyzes feature patterns from missed events
- Evidence extracted: shell process spawning, remote tool usage, lateral movement

### 4. RULE_PROPOSED → RULE_VALIDATED
- Heuristic rule generated from evidence patterns
- Rule validated against replay of same scenario

### 5. REPLAYING → CAUGHT
- Same scenario telemetry replayed with new rule applied
- Attack events now correctly flagged by detector
- `self_correction_status = CAUGHT`

### 6. BLASTSCOPE
- NetworkX graph traversal from compromised host
- Blast radius score computed and persisted on incident

### 7. WHAT-IF
- Logistic Regression counterfactual analysis
- Risk delta computed: "what if this feature were different?"

### 8. SEAL
- Incident transitioned to `SEALED` status
- Audit record appended with `action = incident_sealed`

### 9. AUDIT VERIFICATION
- `verify_chain()` confirms hash chain integrity
- All 9 audit records linked correctly
- No tampering detected

## Test verification

```bash
python -m pytest tests/ -v
```

49 tests verify:
- Incident lifecycle state machine transitions
- Self-correction state machine (MISS → CAUGHT)
- Audit chain integrity and tamper detection
- Synthetic data determinism and replay identity
- Feature extraction correctness
- ML model training and inference
- BlastScope graph simulation
- FastAPI endpoint behavior
- Full demo orchestration end-to-end

## Observable artifacts

Each demo run produces:
- Incident record in database with full lifecycle
- 9 audit records with hash-chained integrity
- Detection records (pre-patch miss, post-patch catch)
- BlastScope simulation record
- What-If counterfactual analysis record
- Rule proposal and validation record
- Replay record with identical telemetry
