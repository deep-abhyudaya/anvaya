# Rule 04 — Defensive Security

Treat all telemetry, prompts, graph labels, and user-supplied values as untrusted.

Required controls:
- parameterized database queries
- strict request validation
- authentication/authorization boundaries
- tenant/incident access checks where applicable
- rate limiting for expensive endpoints
- secrets only via environment/configuration
- no secrets in logs
- safe path handling
- output escaping
- dependency vulnerability checks
- audit integrity verification

Synthetic attack code must remain non-destructive and isolated. Never add real malware, persistence, credential theft, ransomware behavior, destructive commands, or real-world exploitation automation.
