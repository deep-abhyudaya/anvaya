# PHASE 4 — VERIFICATION, RECOVERY, DELEGATION

Strengthen the existing agent execution so it can challenge its own conclusions, recover from failure, and use the existing subagent framework intelligently.

## Verification gate

Never allow:

`model conclusion → final finding`

Require:

`candidate finding → evidence verification → accepted/rejected → final`

Verification should check, where applicable:

- evidence references exist
- timestamps are coherent
- graph relationships exist
- required tools completed successfully
- provenance matches current project/dataset/generation
- result is not contradicted by stronger evidence
- mission success condition is actually met

## Recovery

For each failed tool:

1. capture failure
2. classify failure
3. decide retry/alternative/stop
4. update execution state
5. replan

Do not silently swallow errors.

Example:

`trace_attack_path failed because graph is incomplete`

Next action:

`search event correlations instead`

The system must demonstrate that this is possible through real code, not a hardcoded UI message.

## Partial results

If one subtask fails but the overall mission remains solvable:

- mark subtask failed
- continue independent work
- downgrade confidence appropriately
- final answer must acknowledge the missing evidence

## Subagents

Reuse `SubagentSpawner` / `SubagentExecution`.

The parent agent should delegate only when useful.

Good delegation:

- Network analysis
- Timeline analysis
- Identity correlation

Bad delegation:

- a subagent whose only purpose is to animate the UI
- duplicate artifact generation already being done by the parent

The parent must receive structured results and decide whether they change the mission.

## Cancellation

Integrate cooperative cancellation with existing execution/subagent state.

No forced process termination.

When cancelled:

- persist cancellation state
- emit cancellation event
- stop future tool selection
- preserve completed evidence

## Acceptance tests

1. Primary tool fails → alternative succeeds → mission completes.
2. Verification rejects candidate → agent investigates again.
3. Parent delegates two real subtasks → synthesizes results.
4. User cancellation stops a long-running mission without false completion.
