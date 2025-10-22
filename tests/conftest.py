import pytest
import sqlite3
from unittest.mock import patch
import sys

# Adjust the python path to import the module
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core import database

class MockConnectionWrapper:
    """A wrapper around a real sqlite3 connection that intercepts the close() call."""
    def __init__(self, real_conn):
        self._real_conn = real_conn

    def close(self):
        # This is the magic: we do nothing when close() is called by the application code.
        pass

    def __getattr__(self, name):
        # Delegate all other attribute access (e.g., .cursor(), .commit())
        # to the real connection object.
        return getattr(self._real_conn, name)

@pytest.fixture
def db_connection():
    """
    Pytest fixture that patches `sqlite3.connect` to use a single, shared
    in-memory database for the duration of a test. This prevents functions from
    closing the connection prematurely.
    """
    real_conn = sqlite3.connect(":memory:")
    mock_conn_wrapper = MockConnectionWrapper(real_conn)

    with patch('core.database.sqlite3.connect', return_value=mock_conn_wrapper):
        database.setup_database()
        yield mock_conn_wrapper # Yield the wrapped connection

    real_conn.close()


# Фикстура для управления event loop и предотвращения конфликта между pytest-asyncio и pytest-playwright
@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Fix for the asyncio event loop issue with pytest-playwright
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session scope."""
    import asyncio
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
