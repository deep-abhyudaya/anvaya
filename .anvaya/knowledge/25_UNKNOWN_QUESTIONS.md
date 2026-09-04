# ANVAYA — Unknown / Needs Verification

> Questions that cannot be answered from the repository alone. Mark resolved items with date and source.

## Open questions

1. **Production Postgres migration path**
   - `migrations.py` only handles SQLite column additions. Is there a real Alembic migration chain for production?
   - Status: UNKNOWN
   - Needed from: human / devops

3. **UI reference images currency**
   - `.devin/references/ui/` contains nine images. Are these still the exact visual source of truth, or have they been superseded?
   - Status: UNKNOWN
   - Needed from: human / judge requirements

4. **Docker usage in judge demo**
   - Is the `docker-compose.yml` the canonical runtime for demos, or is Railway/Fly.io expected?
   - Status: UNKNOWN
   - Needed from: human / deployment docs

5. **Gmail service-account setup**
   - `GmailAdapter` expects a credentials file path. What is the exact OAuth/service-account setup process?
   - Status: UNKNOWN
   - Needed from: human / Google Cloud console

6. **Swytchcode integration contract**
   - `SwytchcodeAdapter` is currently hard-disabled. What is the real Swytchcode `/v1/execute` contract?
   - Status: UNKNOWN
   - Needed from: human / Swytchcode docs

7. **Lyzr endpoint reality**
   - `LyzrAdapter.propose` calls `api.lyzr.com/v2/llm/chat/completions` with `gpt-4o-mini`. Is this the real Lyzr contract?
   - Status: UNKNOWN
   - Needed from: human / Lyzr docs

8. **Public auth endpoints in production**
   - Better Auth is used locally. How is it deployed and protected in production (email provider, callback URLs, secrets management)?
   - Status: UNKNOWN
   - Needed from: human / deployment plan

9. **Rate limits / DoS protection for `POST /telemetry`**
   - Live scoring creates incidents. Are there rate limits or input validation beyond the FastAPI global exception handler?
   - Status: UNKNOWN
   - Needed from: human / security review

10. **Model versioning and rollback**
    - `ModelVersion` records metrics. Is there a process to roll back to a previous model if a new one degrades?
    - Status: UNKNOWN
    - Needed from: human / data science plan

## Resolved

1. **Launchpad / Signal API exact contract** — resolved 2026-09-04.
   - Canonical host is `https://www.startuped.ai`. Marketing signals use `GET/POST /api/v1/marketing/signals` and `GET/PUT/DELETE /api/v1/marketing/signals/:id`; workspace comes from auth and must not be sent in the body. Launchpad product actions use authenticated organization-scoped APIs including `/api/v1/accounts`, `/api/v1/leads`, `/api/v1/projects`, and `/api/v1/marketing/campaigns`.
   - Source: Startuped developer docs supplied by the user, live OpenAPI `/api/swagger`, and successful live calls.

2. **Startuped signal update semantics** — resolved 2026-09-04.
   - Create with an optional unique `signalKey`, then `PUT /api/v1/marketing/signals/:id` using either the Mongo ID or `signalKey`; send `signalValue` to append a time-series entry. Existing signals with an empty `signalKey` remain updateable by Mongo ID.
   - Source: Startuped Signal API documentation supplied by the user.

## How to close an item

When a question is resolved:
1. Update this file with the answer.
2. Add the source (file, URL, human name).
3. Update the relevant `.anvaya/knowledge/` doc.
4. Add/update active-recall questions if the answer changes the mental model.
