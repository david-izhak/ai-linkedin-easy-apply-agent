import logging
from unittest.mock import MagicMock, AsyncMock
import pytest
from core.database import (
    init_db,
    save_discovered_jobs,
    update_job_status,
    save_enrichment_data,
)
from phases.processing import run_processing_phase
from config import config
import sqlite3
from dataclasses import replace


@pytest.fixture(scope="module")
def db_conn():
    """Fixture to set up an in-memory SQLite database for a test module."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def mock_is_vacancy_suitable(monkeypatch):
    """Fixture to mock the LLM-based suitability check and simulate a failure."""
    mock = MagicMock()
    monkeypatch.setattr("phases.processing.is_vacancy_suitable", mock)
    return mock


@pytest.fixture
def mock_apply_to_job(monkeypatch):
    """Fixture to mock the apply_to_job function."""
    mock = AsyncMock()
    monkeypatch.setattr("phases.processing.apply_to_job", mock)
    return mock


@pytest.fixture
def mock_wait(monkeypatch):
    """Fixture to mock the wait function."""
    mock = AsyncMock()
    monkeypatch.setattr("phases.processing.wait", mock)
    return mock


@pytest.mark.asyncio
async def test_llm_filter_fallback_integration(
    db_conn,
    mock_is_vacancy_suitable,
    mock_apply_to_job,
    mock_wait,
    caplog,
    app_config,
):
    """
    Integration test for the LLM filter fallback mechanism.

    This test verifies that when the primary LLM-based filter (`is_vacancy_suitable`)
    fails with an exception, the system correctly falls back to the secondary,
    word-based filter, and updates the vacancy status accordingly.
    """
    # 1. Setup: Create a vacancy to be checked.
    save_discovered_jobs(
        [(123, "/link1", "Software Engineer", "Tech Corp")], db_conn
    )
    save_enrichment_data(
        123,
        {
            "description": "Must have strong Java and SQL skills.",
            "company_description": "A great place to work.",
        },
        db_conn,
    )

    # 2. Arrange Mocks: Configure the LLM filter to fail.
    mock_is_vacancy_suitable.side_effect = Exception("LLM API is down")
    mock_apply_to_job.return_value = (
        True  # Assume the application itself succeeds
    )

    # Configure Playwright context and page interaction to simulate finding the button
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_locator = AsyncMock()
    # IMPORTANT: The locator should find ZERO instances of the "no longer accepting" text
    # for the application process to continue.
    mock_locator.count = AsyncMock(return_value=0)
    # page.locator is a sync method returning a locator object
    mock_page.locator = MagicMock(return_value=mock_locator)
    mock_context.new_page.return_value = mock_page

    test_config = app_config.model_copy(
        update={
            "session": app_config.session.model_copy(
                update={"db_file": None, "db_conn": db_conn}
            ),
            "job_search": app_config.job_search.model_copy(
                update={"job_description_regex": r"java"}
            ),
        }
    )

    # 3. Act: Run the processing phase.
    await run_processing_phase(
        context=mock_context,
        applications_today_count=0,
        should_submit=True,
        app_config=test_config,
    )

    # 4. Assert: Verify fallback occurred and status was updated.
    assert "LLM filtering failed" in caplog.text
    assert "falling back to word-based filtering" in caplog.text

    # Verify that the job was still processed because it matched the fallback regex
    mock_apply_to_job.assert_awaited_once()
    mock_wait.assert_awaited_once()

    # Check the database to ensure the status was updated to 'processed'
    cursor = db_conn.cursor()
    cursor.execute("SELECT status FROM vacancies WHERE id = 123")
    status = cursor.fetchone()[0]
    assert status == "applied"
