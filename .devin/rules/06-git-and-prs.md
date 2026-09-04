# Rule 06 — Git Hygiene

- Work in focused feature branches.
- Prefer one coherent PR per phase or tightly related fix.
- Do not rewrite shared history.
- Do not commit secrets, `.env`, large model binaries, generated caches, or machine-specific state.
- Keep commits understandable.
- PR descriptions must include:
  - problem
  - implementation
  - tests run
  - known limitations
  - docs updated
  - demo impact

Before opening a PR, review `git diff`, status, and changed-file list.
