---
trigger: always_on
---
# Rule 04 — Security-Sensitive Changes

For security-sensitive operations, explicitly analyze:

- trust boundary
- privileges
- attacker-controlled input
- command execution
- network access
- filesystem access
- authentication
- authorization
- secret handling
- injection risk
- sandbox escape risk
- denial-of-service risk
- logging/auditability
- failure containment

Never weaken isolation merely to simplify implementation. If a security trade-off is required, document it in `.anvaya/knowledge/14_SECURITY_MODEL.md` and `CHANGELOG.md` and escalate to the user.
