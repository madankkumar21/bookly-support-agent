import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bookly.backend import Backend  # noqa: E402
from bookly.config import TODAY  # noqa: E402
from bookly.kb import PolicyText  # noqa: E402
from bookly.policy import Policy  # noqa: E402


@pytest.fixture(autouse=True)
def router_off(monkeypatch):
    """A BOOKLY_ROUTER=1 in .env must not reach the scripted tests: they would call the real router."""
    import bookly.config

    monkeypatch.setattr(bookly.config, "ROUTER_ENABLED", False)


@pytest.fixture(autouse=True)
def jev_off(monkeypatch, tmp_path):
    """Flags in .env must not reach the scripted tests, and no test may spend on or log to the real Jev."""
    import bookly.config

    monkeypatch.setattr(bookly.config, "STORE_ENABLED", False)
    monkeypatch.setattr(bookly.config, "ROUTER_ENGINE", "haiku")
    monkeypatch.setattr(bookly.config, "JEV_LOG", tmp_path / "jev_calls.jsonl")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


@pytest.fixture
def backend() -> Backend:
    return Backend.load()


@pytest.fixture
def policy() -> Policy:
    return Policy.load()


@pytest.fixture
def policy_text(policy) -> PolicyText:
    return PolicyText(policy)


@pytest.fixture
def today():
    return TODAY
