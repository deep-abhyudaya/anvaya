# 01 — What is ANVAYA?

## In one paragraph

ANVAYA is a defensive cyber-security simulator that acts like an autonomous SOC analyst. It watches fake but realistic computer activity (telemetry), flags suspicious behaviour with machine learning, and when it misses an attack it figures out why, writes a new detection rule, replays the same attack to prove the rule works, simulates the damage if the attack had been left alone, and writes an uneditable audit trail. All of this is packaged as a modern web dashboard connected to a Python backend.

## The problem

Real SOC teams are flooded with alerts. Most tools either (a) miss new attacks because they have never seen them before, or (b) drown analysts in false alarms. ANVAYA's core idea is **self-correction**: if the system misses an attack and a human (or a scenario) confirms it was real, the system should learn from that miss on its own and come back with a better rule.

## The solution

1. **Detect** — An Isolation Forest model looks at telemetry events and scores them as normal or suspicious.
2. **Miss deliberately** — A hard scenario (`ATK-MISS-001`) is designed to evade the first model.
3. **Confirm** — Ground-truth labels prove the miss was a real attack.
4. **Backtrack** — The engine walks back through the events and picks out the suspicious features.
5. **Propose** — A new detection rule is proposed (with optional help from an LLM).
6. **Validate** — The rule is tested against historical telemetry.
7. **Replay** — The same attack is replayed with the new rule, and this time it is caught.
8. **BlastScope** — A graph shows how far the attacker could have moved through the network.
9. **What-If** — A Logistic Regression model shows how risk changes if certain features were different.
10. **Seal** — The incident is locked and an audit chain is written.

## Why this matters for a hackathon

- It is a complete end-to-end product, not a notebook or a single model.
- It has a real frontend, backend, database, ML, and audit system.
- The self-correction loop is **judge-observable**: you can run `anvaya demo` and watch it go from miss → caught.
- Every stage is tested, logged, and hashed so the demo is trustworthy.
