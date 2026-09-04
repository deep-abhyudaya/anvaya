---
name: anvaya-autobuild
description: Build, test, evaluate, and validate ANVAYA end-to-end using deterministic synthetic telemetry, ML evaluation, self-correction replay, and judge-mode QA.
---

# ANVAYA AutoBuild Skill

## Use when
- starting a fresh ANVAYA build
- advancing the project to the next phase
- recovering from CI failures
- validating the end-to-end demo

## Procedure
1. Read root `AGENTS.md`.
2. Read `.devin/rules/` files relevant to the task.
3. Read `docs/ARCHITECTURE.md` and `docs/ASSUMPTIONS.md` if present.
4. Inspect repository status and current tests.
5. Identify the current phase from `docs/PROJECT_STATUS.md` or infer it from implemented artifacts.
6. Execute only the next incomplete phase from `.devin/workflow/MASTER_BUILD.md` unless the user explicitly requests a specific phase.
7. Implement the complete vertical slice for that phase.
8. Generate or update tests before declaring completion.
9. Run tests, lint, typecheck, build, and relevant local smoke tests.
10. For ML changes, generate a fresh evaluation report and verify no leakage.
11. For self-correction changes, run the identical pre/post replay proof.
12. Update project status and documentation.
13. Create a focused PR/checkpoint.
14. Continue to the next phase when the acceptance gate is satisfied.

## Failure handling
Do not hide failures. Create a concise diagnostic report with:
- observed failure
- likely root cause
- attempted fix
- result
- remaining blocker

Prefer deterministic local reproductions over vague debugging.
