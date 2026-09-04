# ANVAYA Security Audit

## Defensive scope

ANVAYA is a defensive cyber SOC simulator. All attack scenarios are synthetic, deterministic, and isolated. The system does not contain real-world exploitation automation, malware, persistence, credential theft, or destructive payloads.

## Input validation status

- All HTTP endpoints use Pydantic/SQLModel schemas for request validation.
- `anvaya.routers.*` validate path parameters and query strings.
- `anvaya.models.*` define constrained fields (max_length, indexes, enums).
- No raw SQL is built from user input; SQLModel ORM is used throughout.
- Synthetic data generator uses fixed seed/version templates.

## Audit integrity

- `AuditRecord.compute_hash()` links each record to the previous hash.
- `verify_chain()` detects tampering by recomputing expected hashes without mutating records.
- Timestamps are normalized for storage to handle SQLite timezone differences.
- Records are append-only in the incident lifecycle; `sealed` status prevents further mutation.

## Secrets

- `OPENAI_API_KEY` is required only for optional LLM rule proposal; system falls back to heuristic rule generation.
- Database credentials come from `DATABASE_URL` environment variable.
- No secrets are committed to source control.

## Recommendations

1. Add rate limiting to public API endpoints.
2. Add request-size limits and payload sanitization for `demo`, `whatif`, and `blastscope` endpoints.
3. Add audit-log rotation and encrypted backup for sealed incidents.
4. Consider PostgreSQL row-level security for multi-tenant deployments.
5. Rotate model artifact signing keys in production.
