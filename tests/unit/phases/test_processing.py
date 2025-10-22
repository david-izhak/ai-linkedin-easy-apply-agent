import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import Page, Error as PlaywrightError, TimeoutError
import sqlite3
from dataclasses import dataclass

from core.database import init_db
from phases.processing import _is_job_suitable, _process_single_job, run_processing_phase


@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def app_config(db_conn, app_config):
    """Fixture to create a mock AppConfig with an in-memory db_conn."""
    app_config.session.db_conn = db_conn
    return app_config


class TestIsJobSuitable:
    @pytest.mark.asyncio
    @patch("phases.processing.is_vacancy_suitable", new_callable=AsyncMock)
    async def test_llm_filter_succeeds_and_approves(
        self, mock_llm_filter, app_config
    ):
        mock_llm_filter.return_value = (True, None)
        assert await _is_job_suitable(1, "title", "desc", app_config) is True

    @pytest.mark.asyncio
    @patch("phases.processing.is_vacancy_suitable", new_callable=AsyncMock)
    async def test_llm_filter_succeeds_and_rejects(
        self, mock_llm_filter, app_config
    ):
        mock_llm_filter.return_value = (False, "Low score")
        assert await _is_job_suitable(1, "title", "desc", app_config) is False

    @pytest.mark.asyncio
    @patch("phases.processing.is_vacancy_suitable", new_callable=AsyncMock)
    async def test_llm_filter_fails_fallback_succeeds(
        self, mock_llm_filter, app_config
    ):
        mock_llm_filter.side_effect = Exception("LLM Error")
        app_config.job_search.job_description_regex = r"java"
        assert (
            await _is_job_suitable(1, "title", "description with java", app_config)
            is True
        )

    @pytest.mark.asyncio
    @patch("phases.processing.is_vacancy_suitable", new_callable=AsyncMock)
    async def test_llm_filter_fails_fallback_fails(
        self, mock_llm_filter, app_config
    ):
        mock_llm_filter.side_effect = Exception("LLM Error")
        app_config.job_search.job_description_regex = r"java"
        assert (
            await _is_job_suitable(
                1, "title", "description with python", app_config
            )
            is False
        )


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock()
    coordinator.fill = AsyncMock()
    return coordinator


class TestProcessSingleJob:
    @pytest.mark.asyncio
    @patch("phases.processing.update_job_status")
    @patch("phases.processing.apply_to_job", new_callable=AsyncMock)
    @patch("phases.processing._is_job_suitable", new_callable=AsyncMock)
    async def test_process_single_job_suitable_and_applied(
        self,
        mock_is_suitable,
        mock_apply,
        mock_update_status,
        app_config,
        mock_coordinator,
    ):
        mock_is_suitable.return_value = True
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_page.is_closed.return_value = False
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        job_data = (1, "link", "title", "company", "desc")

        result = await _process_single_job(
            mock_context, job_data, app_config, True, mock_coordinator
        )

        assert result is True
        mock_apply.assert_awaited_once()
        mock_update_status.assert_called_with(
            1, "applied", app_config.session.db_conn
        )

    @pytest.mark.asyncio
    @patch("phases.processing.update_job_status")
    @patch("phases.processing._is_job_suitable", new_callable=AsyncMock)
    async def test_process_single_job_not_suitable(
        self,
        mock_is_suitable,
        mock_update_status,
        app_config,
        mock_coordinator,
    ):
        mock_is_suitable.return_value = False
        mock_context = AsyncMock()
        job_data = (1, "link", "title", "company", "desc")

        result = await _process_single_job(
            mock_context, job_data, app_config, True, mock_coordinator
        )

        assert result is False
        mock_update_status.assert_called_with(
            1, "skipped_filter", app_config.session.db_conn
        )

    @pytest.mark.asyncio
    @patch("phases.processing.update_job_status")
    @patch("phases.processing.apply_to_job", side_effect=TimeoutError("..."))
    @patch("phases.processing._is_job_suitable", new_callable=AsyncMock)
    async def test_process_single_job_timeout_error(
        self,
        mock_is_suitable,
        mock_apply,
        mock_update_status,
        app_config,
        mock_coordinator,
    ):
        mock_is_suitable.return_value = True
        mock_context = AsyncMock()
        mock_page = MagicMock()
        mock_context.new_page.return_value = mock_page
        mock_locator = AsyncMock()
        mock_locator.count = AsyncMock(return_value=0)
        mock_page.locator = MagicMock(return_value=mock_locator)
        mock_page.is_closed.return_value = False
        mock_page.close = AsyncMock()
        job_data = (1, "link", "title", "company", "desc")

        result = await _process_single_job(
            mock_context, job_data, app_config, True, mock_coordinator
        )

        assert result is False
        mock_update_status.assert_called_with(1, "error", app_config.session.db_conn)


class TestRunProcessingPhase:
    @pytest.mark.asyncio
    @patch("phases.processing.get_enriched_jobs")
    @patch("phases.processing._process_single_job", new_callable=AsyncMock)
    @patch("phases.processing.wait", new_callable=AsyncMock)
    @patch("phases.processing.FormFillCoordinator")
    @patch("phases.processing.ModalFlowResources")
    async def test_run_processing_phase_all_jobs_processed(
        self,
        mock_modal_resources,
        mock_form_fill_coordinator,
        mock_wait,
        mock_process_job,
        mock_get_jobs,
        app_config,
    ):
        mock_get_jobs.return_value = [(1, "link", "t", "c", "d"), (2, "link", "t", "c", "d")]
        mock_process_job.return_value = True
        app_config.job_limits.max_jobs_to_process = 2
        mock_form_fill_coordinator.return_value = MagicMock()

        await run_processing_phase(AsyncMock(), 0, True, app_config)

        assert mock_process_job.call_count == 2
        assert mock_wait.call_count == 2

    @pytest.mark.asyncio
    @patch("phases.processing.get_enriched_jobs")
    @patch("phases.processing._process_single_job", new_callable=AsyncMock)
    @patch("phases.processing.wait", new_callable=AsyncMock)
    @patch("phases.processing.FormFillCoordinator")
    @patch("phases.processing.ModalFlowResources")
    async def test_run_processing_phase_limit_reached(
        self,
        mock_modal_resources,
        mock_form_fill_coordinator,
        mock_wait,
        mock_process_job,
        mock_get_jobs,
        app_config,
    ):
        mock_get_jobs.return_value = [(1, "l", "t", "c", "d"), (2, "l", "t", "c", "d")]
        mock_process_job.return_value = True
        app_config.general_settings.max_applications_per_day = 1
        mock_form_fill_coordinator.return_value = MagicMock()

        await run_processing_phase(AsyncMock(), 0, True, app_config)

        mock_process_job.assert_awaited_once()
