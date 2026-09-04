---
trigger: always_on
---
# Rule 01 — Documentation Protocol

Whenever you modify code:

1. Identify affected architecture.
2. Identify affected integrations.
3. Identify affected flows.
4. Identify affected security boundaries.
5. Identify affected documentation.
6. Update the corresponding `.anvaya/knowledge/` documents.
7. Update source references.
8. Update integration diagrams (Mermaid) when necessary.
9. Update active-recall questions if the mental model changed.
10. Add a concise entry to `.anvaya/knowledge/CHANGELOG.md`.

Every code change must leave documentation consistent with the repository.
