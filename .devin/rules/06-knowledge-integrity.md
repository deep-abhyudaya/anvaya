---
trigger: always_on
---
# Rule 06 — Knowledge Integrity

Before declaring a task complete, run a documentation consistency check:

```text
[ ] source matches documentation
[ ] architecture diagram is still accurate
[ ] API contracts are current
[ ] integration graph is current
[ ] security assumptions are current
[ ] active recall answers are current
[ ] no obsolete file references remain
[ ] no unsupported architectural claims exist
[ ] important new concepts are documented
```

If you cannot verify something, mark it `UNKNOWN — NEEDS VERIFICATION`. Never silently fabricate certainty.
