---
trigger: always_on
---
# Rule 02 — Architecture Change Protocol

Whenever a change modifies:

- API contracts
- service boundaries
- component relationships
- event flow
- state management
- process execution
- isolation
- authentication/authorization
- detection logic
- incident response
- AI orchestration
- external integrations
- configuration architecture

perform an architecture impact review and append to `.anvaya/knowledge/CHANGELOG.md` or a temporary `docs/ARCHITECTURE_IMPACT.md` if the change is large.

Document:

```text
WHAT CHANGED
WHY
BEFORE
AFTER
DEPENDENCIES
AFFECTED FLOWS
SECURITY IMPACT
FAILURE IMPACT
MIGRATION/COMPATIBILITY IMPACT
DOCUMENTATION UPDATED
```
