import pytest
from unittest.mock import MagicMock
from src.store import Store


@pytest.fixture
def store():
    """In-memory SQLite store — isolated per test."""
    return Store(":memory:")


@pytest.fixture
def notifier():
    """Mock notifier — tracks calls without sending Slack messages."""
    return MagicMock()
