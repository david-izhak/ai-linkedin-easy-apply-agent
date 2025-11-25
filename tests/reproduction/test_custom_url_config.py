import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from config import AppConfig, JobSearchConfig, WorkplaceConfig, JobLimitsConfig
from actions.fetch_jobs import fetch_job_links_user

@pytest.mark.asyncio
async def test_fetch_job_links_user_with_custom_url():
    # Mock AppConfig
    mock_config = MagicMock(spec=AppConfig)
    
    # Setup job_search mock
    mock_config.job_search = MagicMock(spec=JobSearchConfig)
    mock_config.job_search.custom_job_search_url = "https://www.linkedin.com/jobs/collections/top-applicant/"
    mock_config.job_search.keywords = "Software Engineer"
    mock_config.job_search.geo_id = "123"
    mock_config.job_search.distance = "25"
    mock_config.job_search.job_search_period_seconds = 86400
    mock_config.job_search.sort_by = "DD"
    mock_config.job_search.job_title_regex = ".*"

    # Setup workplace mock
    mock_config.workplace = MagicMock(spec=WorkplaceConfig)
    mock_config.workplace.on_site = True
    mock_config.workplace.remote = True
    mock_config.workplace.hybrid = True

    # Setup job_limits mock
    mock_config.job_limits = MagicMock(spec=JobLimitsConfig)
    mock_config.job_limits.max_jobs_to_discover = 10

    # Mock Page
    mock_page = AsyncMock()
    mock_page.navigate = AsyncMock()
    
    # Mock DB Connection
    mock_db_conn = MagicMock()

    # Mock get_resilience_executor to return a mock that has navigate
    mock_executor = AsyncMock()
    mock_executor.navigate = AsyncMock()
    
    with patch("actions.fetch_jobs.get_resilience_executor", return_value=mock_executor):
        # Mock _get_total_job_count to return 0 so we don't enter the loop
        with patch("actions.fetch_jobs._get_total_job_count", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 0
            
            await fetch_job_links_user(mock_page, mock_config, mock_db_conn)

            # Verify navigate was called with custom URL
            mock_executor.navigate.assert_called_with(
                "https://www.linkedin.com/jobs/collections/top-applicant/",
                wait_until="load",
                referer="https://www.linkedin.com/jobs/"
            )

@pytest.mark.asyncio
async def test_fetch_job_links_user_without_custom_url():
    # Mock AppConfig
    mock_config = MagicMock(spec=AppConfig)
    
    # Setup job_search mock
    mock_config.job_search = MagicMock(spec=JobSearchConfig)
    mock_config.job_search.custom_job_search_url = None
    mock_config.job_search.keywords = "Software Engineer"
    mock_config.job_search.geo_id = "123"
    mock_config.job_search.distance = "25"
    mock_config.job_search.job_search_period_seconds = 86400
    mock_config.job_search.sort_by = "DD"
    mock_config.job_search.job_title_regex = ".*"

    # Setup workplace mock
    mock_config.workplace = MagicMock(spec=WorkplaceConfig)
    mock_config.workplace.on_site = True
    mock_config.workplace.remote = True
    mock_config.workplace.hybrid = True

    # Setup job_limits mock
    mock_config.job_limits = MagicMock(spec=JobLimitsConfig)
    mock_config.job_limits.max_jobs_to_discover = 10

    # Mock Page
    mock_page = AsyncMock()
    
    # Mock DB Connection
    mock_db_conn = MagicMock()

    # Mock get_resilience_executor
    mock_executor = AsyncMock()
    mock_executor.navigate = AsyncMock()

    with patch("actions.fetch_jobs.get_resilience_executor", return_value=mock_executor):
        # Mock _get_total_job_count to return 0
        with patch("actions.fetch_jobs._get_total_job_count", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 0
            
            await fetch_job_links_user(mock_page, mock_config, mock_db_conn)

            # Verify navigate was called with constructed URL
            # We check if it starts with the base search URL
            args, _ = mock_executor.navigate.call_args
            assert args[0].startswith("https://www.linkedin.com/jobs/search/")
