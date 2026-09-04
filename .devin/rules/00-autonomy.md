# Rule 00 — Autonomous Delivery Protocol

Operate in a closed-loop engineering cycle:

`inspect → plan → implement → run → measure → diagnose → fix → re-run → document → commit/PR`

Do not stop merely because code compiles. Stop a phase only when its acceptance criteria pass.

## Context strategy
Before each non-trivial edit:
1. inspect relevant files;
2. identify existing abstractions;
3. locate tests and conventions;
4. read the nearest applicable instruction/skill file;
5. make the smallest coherent change.

After each non-trivial edit:
1. run the narrowest relevant test;
2. then run broader checks;
3. inspect failures;
4. fix root causes;
5. rerun until green or clearly blocked.

## Decision heuristic
When deciding between alternatives, prioritize:
1. correctness
2. reproducibility
3. testability
4. simplicity
5. performance
6. implementation speed
7. cosmetic polish

Never reverse this priority order merely to produce a flashy demo.
