# 11 — Testing

## Test suite

Tests live in `tests/` and use **pytest**.

```
tests/
├── conftest.py          # Shared fixtures
├── test_api.py          # FastAPI endpoint integration tests
├── test_audit.py        # Audit chain and tamper detection
├── test_blastscope.py   # NetworkX blast-radius engine
├── test_data_factory.py # Synthetic data determinism
├── test_features.py     # Feature extraction
├── test_incident.py     # Incident lifecycle state machine
└── test_self_correction.py # Full miss → caught self-correction loop
```

## What is being checked

| Test file | What it proves |
|---|---|
| `test_incident.py` | Lifecycle and self-correction state machines only allow valid transitions |
| `test_audit.py` | Hash chains detect tampering; `verify_chain()` returns `False` if a record is altered |
| `test_data_factory.py` | The same seed produces identical telemetry; replay events are identical to originals |
| `test_features.py` | Feature extraction matches the expected 12 columns and values |
| `test_api.py` | Endpoints return the right status codes, shapes, and error messages |
| `test_blastscope.py` | Graph building, reachability, and impact scoring work |
| `test_self_correction.py` | The whole `MISS → CAUGHT` cycle runs end-to-end |

## Running the tests

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests with verbose output
python -m pytest tests/ -v
```

## Test coverage

The project has 49 tests covering:
- State machines
- Audit integrity
- Synthetic data
- ML feature extraction
- Model training and inference
- BlastScope graph simulation
- FastAPI endpoints
- Full demo orchestration

This is the safety net that makes sure the judge demo works every time.
