# ANVAYA — Threat Model

> ANVAYA is a defensive simulator. This threat model covers the application, not real network attacks.

## Assets

- **Database:** incidents, telemetry, rules, audit chain, project artifacts.
- **Models:** trained joblib files in `ml/artifacts/`.
- **Credentials:** API keys in `.env`/`.env.local`, Gmail service-account file.
- **Reputation:** truthful provider attribution, audit integrity.
- **Availability:** backend, frontend, CLI.

## Attack surfaces

### 1. `POST /telemetry`

- **Threat:** attacker floods fake events to create incidents or DoS.
- **Mitigation:** authentication not enforced on this endpoint today; production should add rate limiting and auth.
- **Status:** rate limiting is UNKNOWN — see `25_UNKNOWN_QUESTIONS.md`.

### 2. Agent tool execution

- **Threat:** prompt injection causes the agent to call a dangerous tool or pass malicious input.
- **Mitigation:** tool allowlist, strict parameter validation, `requires_confirmation` for high-risk tools, no `exec`/`eval`.

### 3. `_do_shell` in CLI

- **Threat:** user or compromised agent runs arbitrary commands.
- **Mitigation:** only available in interactive CLI, not exposed via API; runs with user privileges.

### 4. External adapter credential exposure

- **Threat:** API keys leak to logs or frontend.
- **Mitigation:** keys in `Settings`; never sent to frontend; logging avoids secrets.

### 5. Audit record tampering

- **Threat:** attacker modifies `AuditRecord` in DB.
- **Mitigation:** hash chain; `verify_chain` detects tampering; DB access control.

### 6. LLM output execution

- **Threat:** model suggests code or commands that get executed.
- **Mitigation:** no `exec`/`eval`; LLM only proposes plans which are validated and then mapped to allowlisted tools.

### 7. Markdown XSS

- **Threat:** malicious markdown rendered in UI.
- **Mitigation:** `rehype-sanitize` in `frontend/components/agent/markdown-renderer.tsx`.

### 8. CORS misconfiguration

- **Threat:** allow untrusted origins to call the API.
- **Mitigation:** `cors_origins` list in `config.py`; default localhost only.

### 9. Better Auth token forgery

- **Threat:** attacker forges session token.
- **Mitigation:** HMAC-SHA256 with `BETTER_AUTH_SECRET`; secret must be strong.

### 10. Model/data poisoning

- **Threat:** attacker injects bad training data.
- **Mitigation:** synthetic data is deterministic and isolated; CSV import can be validated by `DataFactory.validate`.

## Risk matrix

| Threat | Severity | Likelihood | Risk |
|--------|----------|------------|------|
| Telemetry flood | High | Medium | High |
| Prompt injection | Medium | Medium | Medium |
| CLI shell | High | Low | Medium |
| Credential leak | High | Low | Medium |
| Audit tampering | Medium | Low | Low |
| LLM output exec | High | Low | Medium |
| Markdown XSS | Medium | Low | Low |
| CORS misconfig | Medium | Low | Low |
| Auth token forge | High | Low | Medium |
| Data poisoning | Medium | Low | Low |

## Active recall

- What is the highest-severity threat in this model?
- How is audit tampering detected?
- Why is `_do_shell` not exposed via the API?
- What sanitizes markdown in the frontend?
- What is the current status of telemetry rate limiting?

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/models/audit.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/auth.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/agent/executor.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/backend/anvaya/main.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/frontend/components/agent/markdown-renderer.tsx" />
