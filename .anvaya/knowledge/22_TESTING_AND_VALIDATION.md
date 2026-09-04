# ANVAYA — Testing and Validation

## Test layout

- `tests/` — high-level integration and feature tests.
- `backend/anvaya/tests/` — smaller focused tests.
- `pyproject.toml` `tool.pytest.ini_options` sets `testpaths = ["tests"]` and `asyncio_mode = auto`.

## Key test files

| Test | Coverage |
|------|----------|
| `tests/test_live_scoring.py` | `score_and_maybe_flag` with and without model |
| `tests/test_agent.py` | Agent orchestration, tool execution |
| `tests/test_provider_adapters.py` | Tavily, n8n, Gmail, Lyzr, Swytchcode fallback |
| `tests/test_llm_providers.py` | LLM provider catalog and fallbacks |
| `tests/test_blastscope.py` | BlastScope graph traversal |
| `tests/test_self_correction.py` | Sentinel backtrack → replay |
| `tests/test_artifact_generation.py` | Project artifact build |
| `tests/test_builder_streaming.py` | Build event stream |
| `tests/test_cli.py` | CLI commands |
| `tests/test_api.py` | Basic API routes |
| `tests/test_demo_batch.py` | Multi-incident batch demo |
| `tests/test_data_factory.py` | Synthetic data generation |
| `tests/test_world_architect.py` | World model generation |
| `backend/anvaya/tests/test_train_command.py` | `/train` command |

## Running tests

```bash
cd /home/de3p/Documents/Next.js/Anavaya
python -m pytest tests/ -q --no-header
```

Focused set:

```bash
cd /home/de3p/Documents/Next.js/Anavaya
python -m pytest tests/test_live_scoring.py tests/test_agent.py tests/test_provider_adapters.py tests/test_self_correction.py -v
```

## Lint / type

- `ruff` configured in `pyproject.toml` (`line-length = 100`, target `py311`).
- `mypy` configured (`python_version = "3.14"`, `ignore_missing_imports = true`).
- Frontend lint: `npm --prefix frontend run lint` (ESLint 9 + `eslint-config-next`).

## Baseline

Per `.devin/rules/rules.md`: default test run should be `pytest tests/ -q --no-header`. The current baseline is 309 passed, 15 failed (pre-existing unrelated failures in catalog intelligence, CLI validation, and LLM provider tests).

Focused batch demo tests:

```bash
.venv/bin/pytest tests/test_self_correction.py tests/test_demo_batch.py -q
```

## Validation practices

- **No external credentials by default:** tests use SQLite and mocked HTTP.
- **Live-API tests** should be marked `@pytest.mark.live` and not run by default.
- **ML tests** use deterministic seeds and synthetic data.
- **Audit tests** verify hash chain.
- **Integration tests** verify the `miss → catch → blast → what-if → audit` flow.

## Active recall

- What is the default test command?
- Where are focused backend tests?
- How are live API tests marked?
- What is the lint tool for the backend?
- Are there known pre-existing test failures? (Yes, 14)

## Source references

- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/pyproject.toml" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/tests/test_live_scoring.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/tests/test_provider_adapters.py" />
- <ref_file file="/home/de3p/Documents/Next.js/Anavaya/.devin/rules/rules.md" />
