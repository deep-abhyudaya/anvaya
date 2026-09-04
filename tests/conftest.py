"""Test configuration and fixtures."""

import atexit
import os
import shutil
import tempfile
from collections.abc import Generator

import pytest
from sqlmodel import Session, SQLModel, create_engine

os.environ["DATABASE_URL"] = "sqlite:///./test_anvaya.db"
os.environ["DEBUG"] = "false"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

os.environ["NVIDIA_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["AGENTROUTER_API_KEY"] = ""
os.environ["OPENCODE_API_KEY"] = ""
os.environ["SEEKAI_API_KEY"] = ""
os.environ["GMICLOUD_API_KEY"] = ""
os.environ["EMPERO_API_KEY"] = "disabled"

_test_home = tempfile.mkdtemp(prefix="anvaya-test-")
os.environ["HOME"] = _test_home
atexit.register(shutil.rmtree, _test_home, True)


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture()
def mock_frontier_model():
    """Return a mock ModelConfig with quality_class='frontier'."""
    from unittest.mock import MagicMock

    model = MagicMock()
    model.id = "test-frontier-model"
    model.provider = "test"
    model.display_name = "Test Frontier Model"
    model.quality_class = "frontier"
    model.default_temperature = 0.1
    model.context_window = 128000
    return model


@pytest.fixture()
def mock_frontier_provider():
    """Return a mock model provider that returns canned NextActionContract responses."""
    import json
    from unittest.mock import MagicMock

    provider = MagicMock()
    provider.name = "test"

    def _configured():
        return True

    provider.configured = _configured

    call_count = {"n": 0}

    def _chat_completion(messages, **kwargs):
        call_count["n"] += 1
        resp = MagicMock()
        if call_count["n"] == 1:
            resp.to_dict.return_value = {
                "text": json.dumps({
                    "action": "finish",
                    "reason": "Task complete.",
                    "summary": "Test execution finished.",
                })
            }
        else:
            resp.to_dict.return_value = {
                "text": json.dumps({
                    "action": "finish",
                    "reason": "Already done.",
                    "summary": "Nothing more to do.",
                })
            }
        return resp

    provider.chat_completion = _chat_completion
    return provider

