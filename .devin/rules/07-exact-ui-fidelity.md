# Exact UI Fidelity Rule

The supplied ANVAYA UI references are hard requirements.

Before changing any visual design, compare the implementation against `.devin/references/ui/` and `docs/ui/ANVAYA_UI_SOURCE_OF_TRUTH.md`.

Never replace a reference design with an agent-created alternative. Never call a page complete based only on code quality. Render it at 1672x941 and visually verify it.

Prioritize corrections in this order:
1. page geometry
2. shell dimensions
3. component placement
4. graph topology / structural relationships
5. typography scale and alignment
6. semantic states
7. borders and glow
8. microcopy / minor spacing

If an implementation looks like a normal SaaS dashboard instead of the reference cyber-console, treat that as a failed acceptance criterion.
