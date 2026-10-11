import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bookly.backend import Backend  # noqa: E402
from bookly.config import TODAY  # noqa: E402
from bookly.kb import PolicyText  # noqa: E402
from bookly.policy import Policy  # noqa: E402


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
