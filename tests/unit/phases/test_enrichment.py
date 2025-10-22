import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import Page, Error as PlaywrightError, BrowserContext
from dataclasses import dataclass, field

from config import AppConfig
from phases.enrichment import run_enrichment_phase

@dataclass
class MockSessionConfig:
    db_conn: MagicMock = field(default_factory=MagicMock)

@dataclass
class MockJobLimitsConfig:
    max_jobs_to_enrich: int = 5

@dataclass
class MockAppConfig:
    session: MockSessionConfig = field(default_factory=MockSessionConfig)
    job_limits: MockJobLimitsConfig = field(default_factory=MockJobLimitsConfig)
    general_settings: MagicMock = field(default_factory=MagicMock)

@pytest.fixture
def mock_config():
    cfg = MagicMock(spec=AppConfig)
    cfg.general_settings.wait_between_enrichments_ms = 0
    return cfg

@pytest.fixture
def mock_app_config():
    """Fixture for a mock AppConfig."""
    cfg = MagicMock(spec=AppConfig)
    cfg.general_settings = MagicMock()
    cfg.general_settings.wait_between_enrichments_ms = 0
    cfg.session = MagicMock()
    cfg.session.db_conn = MagicMock()
    cfg.job_limits = MagicMock()
    cfg.job_limits.max_jobs_to_enrich = 50
    return cfg


@pytest.fixture
def mock_browser_context():
    """Fixture for a mock BrowserContext."""
    return AsyncMock(spec=BrowserContext)


class TestRunEnrichmentPhase:
    @pytest.mark.asyncio
    @patch("phases.enrichment.get_jobs_to_enrich")
    @patch("phases.enrichment._enrich_single_job", new_callable=AsyncMock)
    async def test_run_enrichment_phase_no_jobs(
        self, mock_enrich_single_job, mock_get_jobs_to_enrich, mock_app_config, mock_browser_context
    ):
        """Test run_enrichment_phase when no jobs are discovered."""
        mock_get_jobs_to_enrich.return_value = []

        await run_enrichment_phase(mock_app_config, mock_browser_context)

        mock_get_jobs_to_enrich.assert_called_once()
        mock_enrich_single_job.assert_not_called()


    @pytest.mark.asyncio
    @patch("phases.enrichment.get_jobs_to_enrich")
    @patch("phases.enrichment._enrich_single_job", new_callable=AsyncMock)
    async def test_run_enrichment_phase_success(
        self, mock_enrich_single_job, mock_get_jobs_to_enrich, mock_app_config, mock_browser_context
    ):
        """Test the successful run of the enrichment phase."""
        jobs = [(1, "/job1", "Title1", "Company1"), (2, "/job2", "Title2", "Company2")]
        mock_get_jobs_to_enrich.return_value = jobs

        await run_enrichment_phase(mock_app_config, mock_browser_context)

        mock_get_jobs_to_enrich.assert_called_once()
        assert mock_enrich_single_job.call_count == 2
        mock_enrich_single_job.assert_any_call(
            mock_browser_context, 1, "/job1", "Title1", mock_app_config
        )
        mock_enrich_single_job.assert_any_call(
            mock_browser_context, 2, "/job2", "Title2", mock_app_config
        )
