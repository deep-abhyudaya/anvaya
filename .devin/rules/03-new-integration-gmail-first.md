# Workflow: Add a new provider integration (Gmail, then LinkedIn/Instagram/X)

Goal: earn "integrations" XP by adding at least one real, working
integration from the required list (Gmail, LinkedIn, Instagram, X) that
doesn't exist anywhere in the codebase yet (confirmed — see
`.devin/rules.md` Rule 1).

## Why Gmail first

Gmail via a Google Cloud service account or OAuth app is typically the
fastest of the four to actually stand up without an app-review/approval
delay — LinkedIn, Instagram (Meta), and X all commonly gate API access
behind developer app review that can take days, which doesn't fit a
hackathon timeline. Confirm current access requirements for whichever
you attempt before committing time — platform API policies change.

## Step 1 — Decide the actual use case before writing code

Do not build a generic "send an email" integration with no product
purpose — tie it to something ANVAYA already does. Strongest fit,
based on the existing codebase: **email the SOC team when an incident
is sealed, or the moment a genuinely live attack is detected** — the
same `on_incident_event` dispatch point from Workflow 00 / Rule 2a,
with `event_type=DETECTED` or `event_type=SEALED`, is the correct
trigger. This makes Gmail a third parallel step alongside Tavily
enrichment and n8n/Signal-API push inside that same function, not a
competing subsystem — reuse the dispatch discipline from Rule 2a rather
than adding a new call site.

If LinkedIn/Instagram/X is pursued instead, pick an equally concrete,
justified use case (e.g. auto-posting a sanitized summary of a sealed
incident as a transparency/compliance signal), and hook it into the
same dispatch point — do not build an integration with no real trigger
just to check the box.

## Step 2 — Build following the existing adapter pattern exactly

Per `.devin/rules.md` Rule 2:
1. `GmailAdapter` class in `backend/anvaya/agent/adapters.py`, same
   shape as `TavilyAdapter`/`N8NAdapter`: `name = "gmail"`,
   `env_var = "GMAIL_..."` (decide the right credential shape — a
   service account JSON path, or OAuth client id/secret/refresh token;
   Gmail API typically needs `google-api-python-client` +
   `google-auth` — confirm these aren't already in `pyproject.toml`
   before adding as new dependencies, and add them there if not).
2. `configured()`/`healthy()` following the same convention.
3. A `send(to, subject, body)` method (or similarly named) making the
   real Gmail API call, wrapped in try/except, with an honestly-labeled
   local fallback (e.g. log the intended email content and mark
   `fallback_used: true`) on failure or when not configured — mirror
   `N8NAdapter.trigger`'s exact fallback shape.
4. Settings field `gmail_credentials_path` or equivalent in
   `config.py`, plus `is_gmail_enabled()`.
5. `ToolDefinition` in `registry.py` (e.g. `name="notify_via_email"`,
   `category="notification"`, `provider="gmail"`,
   `fallback_provider="anvaya"`, `requires_confirmation=True` since
   this sends real external communication).
6. Handler in `executor.py` (`handle_notify_via_email`) following the
   `handle_trigger_automation` shape exactly.
7. Wire the call site: inside `on_incident_event` (Rule 2a), gated by
   `event_type` (`DETECTED` and/or `SEALED`) and `is_gmail_enabled()` —
   the same shared dispatch point every other integration in this
   project uses, not a separate hook.

## Step 3 — Credentials

Getting a working Gmail credential (service account or OAuth) requires
a human to complete a Google Cloud Console flow — you cannot self-serve
this. Stop and clearly request this from the team the moment you reach
this dependency; do not block all other work waiting for it, continue
with Step 2's code structure using the fallback path, and come back to
verify the live path once the credential exists.

## Step 4 — Tests

- Mock the Gmail API client entirely in tests (don't hit Google's real
  API in the test suite). Assert the adapter correctly maps ANVAYA's
  incident data into a real, well-formed email payload.
- Assert the not-configured fallback path logs/records the intended
  email rather than silently dropping it.

## Step 5 — Report back (required, see Rule 7)

- Exact new files/functions added, mirroring the adapter pattern
  reference points.
- Live-verified or blocked-on-credential (name the exact credential
  needed and who needs to obtain it).
- Test command and result.
- If pursued instead of/in addition to Gmail: which of
  LinkedIn/Instagram/X, and why (access feasibility within the
  hackathon timeline) — don't silently substitute without explaining.
