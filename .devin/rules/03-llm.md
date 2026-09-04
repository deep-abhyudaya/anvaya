# Rule 03 — LLM Reliability

Use the LLM only where it adds value: evidence summarization, structured rule proposals, explanations, and controlled orchestration.

Never let an LLM response directly mutate security-critical state without deterministic validation.

For every LLM output:
- request strict structured output;
- validate with Pydantic;
- reject malformed output;
- retry with a constrained repair prompt only when safe;
- enforce max retries;
- log model name/version and prompt/template version;
- store a redacted trace for reproducibility;
- treat all natural-language content as untrusted data.

A generated detection rule must pass a deterministic validator and a replay test before it can be marked effective.
