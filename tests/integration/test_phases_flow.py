import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sqlite3

from config import config
from core import database
from phases.discovery import run_discovery_phase
from phases.enrichment import run_enrichment_phase
from phases.processing import run_processing_phase


@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    database.init_db(conn)
    yield conn
    conn.close()


class TestPhasesFlow:
    @pytest.mark.asyncio
    @patch("phases.discovery.fetch_job_links_user", new_callable=AsyncMock)
    @patch("phases.enrichment.fetch_job_details", new_callable=AsyncMock)
    @patch("phases.processing.apply_to_job", new_callable=AsyncMock)
    async def test_full_end_to_end_flow(
        self,
        mock_apply,
        mock_fetch_details,
        mock_fetch_links,
        db_conn,
        monkeypatch,
        app_config,
    ):
        """Tests the flow of data between discovery, enrichment, and processing phases."""

        # --- 1. ARRANGE ---
        # Mock config to speed up tests
        test_config = app_config.model_copy(
            update={
                "general_settings": app_config.general_settings.model_copy(
                    update={
                        "wait_between_enrichments_ms": 0,
                        "wait_between_submissions_ms": 0,
                    }
                ),
                "job_limits": app_config.job_limits.model_copy(
                    update={"max_jobs_to_discover": 5, "max_jobs_to_enrich": 5}
                ),
                "bot_mode": app_config.bot_mode.model_copy(
                    update={"mode": "full_run_submit"}
                ),
                "session": app_config.session.model_copy(
                    update={"db_file": None, "db_conn": db_conn}
                ),
                "job_search": app_config.job_search.model_copy(
                    update={"job_description_languages": ["english"]}
                ),
            }
        )
        # Mock return values
        discovered_jobs = [(123, "/job1", "Software Engineer", "TestCo")]
        enriched_details = {
            "description": "A job requiring python skills.",
            "company_description": "A stable company.",
        }
        mock_fetch_links.return_value = discovered_jobs
        mock_fetch_details.return_value = enriched_details
        mock_apply.return_value = None  # apply_to_job returns None
        async def mock_is_suitable(*args):
            return True

        monkeypatch.setattr(
            "phases.processing._is_job_suitable", mock_is_suitable
        )

        # --- 2. ACT ---
        # Run discovery and manually save to simulate its effect on the DB
        await run_discovery_phase(
            app_config=test_config, browser_context=AsyncMock()
        )
        database.save_discovered_jobs(discovered_jobs, db_conn)

        # Run enrichment and manually save to simulate its effect
        await run_enrichment_phase(
            app_config=test_config, browser_context=AsyncMock()
        )
        database.save_enrichment_data(123, enriched_details, db_conn)

        # Run processing phase
        # Create a properly configured mock context that won't hang on close()
        mock_context = AsyncMock()
        mock_context.close = AsyncMock(return_value=None)
        mock_page = AsyncMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_page.goto = AsyncMock(return_value=None)
        mock_page.is_closed.return_value = False
        mock_page.close = AsyncMock(return_value=None)

        # Correctly mock the locator chain to avoid the 'coroutine has no attribute count' error
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)  # Job is not closed
        mock_page.locator = MagicMock(return_value=mock_locator)

        await run_processing_phase(
            context=mock_context,
            applications_today_count=0,
            should_submit=True,
            app_config=test_config,
        )

        # --- 3. ASSERT ---
        mock_fetch_links.assert_awaited_once()
        mock_fetch_details.assert_awaited_once()
        mock_apply.assert_awaited_once()

        # Verify the final state in the database
        final_status = database.get_vacancy_by_id(123, db_conn)["status"]
        assert final_status == "applied"
