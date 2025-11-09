import pytest
from unittest.mock import AsyncMock, patch, ANY, MagicMock
import sys
import os
from dataclasses import dataclass, replace
import sqlite3

from config import AppConfig, config, WorkplaceConfig # Import config and AppConfig
from core import database
from core.selectors import selectors
from actions.fetch_jobs import (
    _get_total_job_count,
    _extract_job_data_from_page,
    fetch_job_links_user,
    _scrape_job_page_details,
    _scrape_company_about_page,
    fetch_job_details,
)

from pytest_mock import MockerFixture

# Mock SelectorExecutor for testing
mock_executor_instance = AsyncMock()

@pytest.fixture(autouse=True)
def mock_get_selector_executor():
    with patch('actions.fetch_jobs.resilience.get_selector_executor', return_value=mock_executor_instance) as mock:
        # Reset mock's behavior and call history before each test
        mock_executor_instance.reset_mock()
        mock_executor_instance.get_text.side_effect = None
        yield mock

@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    database.init_db(conn)
    yield conn
    conn.close()

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestGetTotalJobCount:
    @pytest.mark.asyncio
    async def test_get_total_job_count_success_first_selector(self):
        """Test successful retrieval with the first selector."""
        mock_page = AsyncMock()
        mock_executor_instance.get_text.return_value = "1,093 results"

        result = await _get_total_job_count(mock_page, "https://example.com/jobs")

        mock_executor_instance.get_text.assert_called_once()
        assert result == 1093

    @pytest.mark.asyncio
    async def test_get_total_job_count_success_second_selector(self):
        """Test successful retrieval with the second selector after the first fails."""
        mock_page = AsyncMock()
        mock_executor_instance.get_text.side_effect = [Exception("Fail"), "Showing 456 jobs"]

        result = await _get_total_job_count(mock_page, "https://example.com/jobs")

        assert mock_executor_instance.get_text.call_count == 2
        assert result == 456

    @pytest.mark.asyncio
    async def test_fallback_to_card_counting(self):
        """Test fallback to counting job cards when all selectors fail."""
        mock_page = AsyncMock()
        mock_executor_instance.get_text.side_effect = Exception("All selectors failed")
        mock_page.query_selector_all.return_value = [1, 2, 3]  # Simulate 3 job cards

        result = await _get_total_job_count(mock_page, "https://example.com/jobs")

        assert mock_executor_instance.get_text.call_count == 3
        assert result == 3

    @pytest.mark.asyncio
    async def test_no_count_found_at_all(self):
        """Test when no selectors match and fallback also finds nothing."""
        mock_page = AsyncMock()
        mock_executor_instance.get_text.side_effect = Exception("All selectors failed")
        mock_page.query_selector_all.return_value = []

        result = await _get_total_job_count(mock_page, "https://example.com/jobs")

        assert mock_executor_instance.get_text.call_count == 3
        assert result == 0


class TestScrapePageForLinks:

    @pytest.mark.asyncio
    async def test_scrape_page_for_links_success(self):
        """Test successful scraping of job links from a page."""
        mock_page = AsyncMock()
        
        # --- Mocks for Listing 1 ---
        mock_listing1 = AsyncMock()
        mock_link1 = AsyncMock()
        mock_title1 = AsyncMock()
        mock_company1 = AsyncMock()
        
        mock_listing1.get_attribute.return_value = "123" # Job ID
        mock_link1.get_attribute.return_value = "/jobs/view/123?some_tracking_params"
        mock_title1.inner_text.return_value = "  Software Engineer  "
        mock_company1.inner_text.return_value = " Company A "
        mock_listing1.query_selector.side_effect = [mock_link1, mock_title1, mock_company1]

        # --- Mocks for Listing 2 ---
        mock_listing2 = AsyncMock()
        mock_link2 = AsyncMock()
        mock_title2 = AsyncMock()
        mock_company2 = AsyncMock()

        mock_listing2.get_attribute.return_value = "456" # Job ID
        mock_link2.get_attribute.return_value = "/jobs/view/456"
        mock_title2.inner_text.return_value = "Data Scientist"
        mock_company2.inner_text.return_value = "Company B"
        mock_listing2.query_selector.side_effect = [mock_link2, mock_title2, mock_company2]

        # --- Mocks for Listing 3 (incomplete, should be skipped) ---
        mock_listing3 = AsyncMock()
        mock_listing3.get_attribute.return_value = "789"
        # Simulate not finding the company element
        mock_listing3.query_selector.side_effect = [AsyncMock(), AsyncMock(), None]
        
        # --- Mock for Listing 4 (placeholder, should be skipped) ---
        mock_listing4 = AsyncMock()
        mock_listing4.get_attribute.return_value = "" # Empty job id

        mock_page.query_selector_all.return_value = [mock_listing1, mock_listing2, mock_listing3, mock_listing4]

        result = await _extract_job_data_from_page(mock_page)

        # Assert correct selector was used
        mock_page.query_selector_all.assert_called_once_with(".scaffold-layout__list-item")
        
        # Assertions
        assert len(result) == 2
        # Check that link is cleaned and text is stripped
        assert result[0] == (123, "/jobs/view/123", "Software Engineer", "Company A")
        assert result[1] == (456, "/jobs/view/456", "Data Scientist", "Company B")

    @pytest.mark.asyncio
    async def test_scrape_page_for_links_no_listings(self):
        """Test handling when no job listings are found on the page."""
        mock_page = AsyncMock()
        mock_page.query_selector_all.return_value = []

        result = await _extract_job_data_from_page(mock_page)

        # Should try the main selector once
        assert mock_page.query_selector_all.call_count == 1
        assert result == []


class TestFetchJobLinksUser:

    @pytest.mark.asyncio
    @patch("actions.fetch_jobs.database.upsert_discovery_state")
    @patch("actions.fetch_jobs.database.save_discovered_jobs")
    @patch("actions.fetch_jobs.database.get_existing_vacancy_ids")
    @patch("actions.fetch_jobs.database.get_discovery_state")
    @patch("actions.fetch_jobs._get_total_job_count")
    @patch("actions.fetch_jobs._extract_job_data_from_page")
    @patch("actions.fetch_jobs.fetch_job_links_limit")
    async def test_fetch_job_links_user_success(
        self,
        mock_fetch_job_links_limit,
        mock_extract_job_data_from_page,
        mock_get_total_job_count,
        mock_get_discovery_state,
        mock_get_existing_vacancy_ids,
        mock_save_discovered_jobs,
        mock_upsert_discovery_state,
        app_config,
    ):
        """Test successful fetching of job links with JOB_TITLE filtering."""
        
        # Setup an in-memory database for this test
        # db_file = ":memory:"
        # database.init_db(db_file)
        
        test_config = app_config.model_copy(
            update={
                "job_search": app_config.job_search.model_copy(
                    update={"job_title_regex": r".*Engineer.*"}
                ),
                "job_limits": app_config.job_limits.model_copy(
                    update={"max_jobs_to_discover": None}
                ),
            }
        )
    
        # Mock page and browser context
        mock_page = AsyncMock()
        mock_page.wait_for_selector.return_value = AsyncMock()
        # Simulate 'Next' button being visible on the first page, but not the second
        mock_page.is_visible.side_effect = [True, False]
    
        # Set a return value for the mocked function
        mock_get_total_job_count.return_value = 10
        mock_fetch_job_links_limit.return_value = None
        mock_extract_job_data_from_page.side_effect = [
            [
                (1, "link1", "Software Engineer", "Company A"),
                (2, "link2", "Data Scientist", "Company B"),
                (3, "link3", "Senior Software Engineer", "Company C"),
            ],
            [
                (4, "link4", "DevOps Engineer", "Company D"),
            ],
        ]
    
        keywords = "software engineer"
        workplace = config.workplace
        geo_id = "102983012"
        distance = "25"
        f_tpr = "r86400"
        sort_by = "DD"

        result = await fetch_job_links_user(
            mock_page, test_config, test_config.session.db_conn
        )

        mock_get_total_job_count.assert_called_once()
        assert mock_extract_job_data_from_page.call_count == 2  # 2 pages
        # The scroll function should be called for each page
        # assert mock_ensure_all_jobs_loaded.call_count == 2
        
        # Result is deduplicated by job_id, and filtered by JOB_TITLE pattern
        assert len(result) == 2  # Only 2 jobs should pass the filter
        assert result[0][0] == 1  # job_id
        assert result[1][0] == 3
        mock_save_discovered_jobs.assert_called_once()
        mock_upsert_discovery_state.assert_called_once()

    @pytest.mark.asyncio
    @patch("actions.fetch_jobs.database.get_discovery_state", return_value=None)
    @patch("actions.fetch_jobs._get_total_job_count")
    async def test_fetch_job_links_user_no_jobs(
        self,
        mock_get_total_job_count: MagicMock,
        mock_get_discovery_state: MagicMock,
        app_config: AppConfig,
        mocker: MockerFixture,
    ):
        """Test handling when no jobs are available."""
        mocker.patch(
            "actions.fetch_jobs.config.job_limits.max_jobs_to_discover",
            10,
        )
        mock_page = AsyncMock()
        mock_get_total_job_count.return_value = 0

        result = await fetch_job_links_user(
            mock_page, app_config, app_config.session.db_conn
        )

        mock_get_total_job_count.assert_called_once()
        assert result == []
        mock_page.goto.assert_called_once()
        mock_get_discovery_state.assert_called_once()


class TestScrapeJobPageDetails:

    @pytest.mark.asyncio
    async def test_scrape_job_page_details_success(self):
        """Test successful scraping of job page details."""
        mock_page = AsyncMock()

        # Mock description and company description elements
        mock_desc_element = AsyncMock()
        mock_desc_element.inner_text.return_value = "Job description here"
        
        mock_comp_desc_element = AsyncMock()
        mock_comp_desc_element.inner_text.return_value = "Company description here"

        mock_page.query_selector.side_effect = [
            mock_desc_element,
            mock_comp_desc_element,
        ]

        # Mock employment type elements
        mock_employment_type1 = AsyncMock()
        mock_employment_type1.inner_text.return_value = "Full-time"
        
        mock_employment_type2 = AsyncMock()
        mock_employment_type2.inner_text.return_value = "Hybrid"
        
        mock_page.query_selector_all.return_value = [
            mock_employment_type1,
            mock_employment_type2,
        ]

        result = await _scrape_job_page_details(mock_page, "/job/123")

        assert result["description"] == "Job description here"
        assert result["company_description"] == "Company description here"
        assert result["employment_type"] == "Full-time, Hybrid"


class TestScrapeCompanyAboutPage:

    @pytest.mark.asyncio
    async def test_scrape_company_about_page_success(self):
        """Test successful scraping of company about page details."""
        mock_page = AsyncMock()
        company_name = "test-company"

        # Mock overview element
        mock_overview_el = AsyncMock()
        mock_page.query_selector.return_value = mock_overview_el
        mock_overview_el.inner_text.return_value = "Company overview here"

        # For the second call (details list)
        mock_details_list = AsyncMock()
        mock_page.query_selector.side_effect = [mock_overview_el, mock_details_list]

        # Mock dt and dd elements
        mock_dt1 = AsyncMock()
        mock_dt2 = AsyncMock()
        mock_dt3 = AsyncMock()
        mock_dd1 = AsyncMock()
        mock_dd2 = AsyncMock()
        mock_dd3 = AsyncMock()

        mock_details_list.query_selector_all.side_effect = [
            [mock_dt1, mock_dt2, mock_dt3],  # dt elements
            [mock_dd1, mock_dd2, mock_dd3],  # dd elements
        ]

        mock_dt1.inner_text.return_value = "Website"
        mock_dt2.inner_text.return_value = "Industry"
        mock_dt3.inner_text.return_value = "Company size"

        mock_dd1.inner_text.return_value = "https://company.com"
        mock_dd2.inner_text.return_value = "Technology"
        mock_dd3.inner_text.return_value = "1001-5000 employees"

        result = await _scrape_company_about_page(mock_page, company_name)

        assert result["company_overview"] == "Company overview here"
        assert result["company_website"] == "https://company.com"
        assert result["company_industry"] == "Technology"
        assert result["company_size"] == "1001-5000 employees"


class TestFetchJobDetails:

    @pytest.mark.asyncio
    @patch("actions.fetch_jobs._scrape_job_page_details")
    @patch("actions.fetch_jobs._scrape_company_about_page")
    async def test_fetch_job_details_success(
        self, mock_scrape_company_about_page, mock_scrape_job_page_details, app_config
    ):
        """Test successful fetching of job details."""
        
        test_config = app_config.model_copy(
            update={
                "performance": app_config.performance.model_copy(
                    update={"selector_timeout": 9876}
                )
            }
        )

        mock_page = AsyncMock()
        job_link = "/jobs/view/1234567890/"

        mock_scrape_job_page_details.return_value = {
            "description": "Job description",
            "company_description": "Company description",
            "employment_type": "Full-time",
        }

        mock_scrape_company_about_page.return_value = {
            "company_overview": "Company overview",
            "company_website": "https://company.com",
            "company_industry": "Technology",
            "company_size": "1001-5000 employees",
        }

        # Mock company profile link element
        mock_company_profile_link = AsyncMock()
        mock_company_profile_link.get_attribute.return_value = "/company/test-company/life"
        mock_page.query_selector.return_value = mock_company_profile_link

        result = await fetch_job_details(mock_page, job_link)

        mock_page.goto.assert_called_once_with(f"https://www.linkedin.com{job_link}", wait_until="load")
        mock_scrape_job_page_details.assert_called_once_with(mock_page, f"https://www.linkedin.com{job_link}")
        mock_page.query_selector.assert_called_once_with(
            selectors["company_profile_link"]
        )
        mock_scrape_company_about_page.assert_called_once_with(
            mock_page, "https://www.linkedin.com/company/test-company/about/"
        )

        # Check that all details are merged correctly
        assert result["description"] == "Job description"
        assert result["company_description"] == "Company description"
        assert result["employment_type"] == "Full-time"
        assert result["company_overview"] == "Company overview"
        assert result["company_website"] == "https://company.com"
        assert result["company_industry"] == "Technology"
        assert result["company_size"] == "1001-5000 employees"

    @pytest.mark.asyncio
    @patch("actions.fetch_jobs._scrape_job_page_details")
    @patch("actions.fetch_jobs._scrape_company_about_page")
    async def test_fetch_job_details_no_company_link(
        self, mock_scrape_company_about_page, mock_scrape_job_page_details, app_config
    ):
        """Test fetching job details when no company link is found."""
        
        test_config = app_config.model_copy(
            update={
                "performance": app_config.performance.model_copy(
                    update={"selector_timeout": 9876}
                )
            }
        )

        mock_page = AsyncMock()
        job_link = "/jobs/view/1234567890/"

        mock_scrape_job_page_details.return_value = {
            "description": "Job description",
            "company_description": "Company description",
        }

        mock_page.query_selector.return_value = None  # No company link found

        result = await fetch_job_details(mock_page, job_link)

        mock_page.goto.assert_called_once_with(f"https://www.linkedin.com{job_link}", wait_until="load")
        mock_scrape_job_page_details.assert_called_once_with(mock_page, f"https://www.linkedin.com{job_link}")
        mock_page.query_selector.assert_called_once_with(
            selectors["company_profile_link"]
        )
        mock_scrape_company_about_page.assert_not_called()

        # Should only have job page details
        assert result["description"] == "Job description"
        assert result["company_description"] == "Company description"
        assert "company_overview" not in result

    @pytest.mark.asyncio
    @patch("actions.fetch_jobs._scrape_job_page_details")
    @patch("actions.fetch_jobs._scrape_company_about_page")
    async def test_fetch_job_details_company_link_exception(
        self, mock_scrape_company_about_page, mock_scrape_job_page_details, app_config
    ):
        """Test fetching job details when an exception occurs processing company link."""
        
        test_config = app_config.model_copy(
            update={
                "performance": app_config.performance.model_copy(
                    update={"selector_timeout": 9876}
                )
            }
        )

        mock_page = AsyncMock()
        job_link = "/jobs/view/1234567890/"

        mock_scrape_job_page_details.return_value = {
            "description": "Job description",
            "company_description": "Company description",
        }

        mock_page.query_selector.side_effect = Exception("Link not found")

        result = await fetch_job_details(mock_page, job_link)

        mock_page.goto.assert_called_once_with(f"https://www.linkedin.com{job_link}", wait_until="load")
        mock_scrape_job_page_details.assert_called_once_with(mock_page, f"https://www.linkedin.com{job_link}")
        mock_page.query_selector.assert_called_once_with(
            selectors["company_profile_link"]
        )
        mock_scrape_company_about_page.assert_not_called()

        # Should only have job page details
        assert result["description"] == "Job description"
        assert result["company_description"] == "Company description"
        assert "company_overview" not in result
