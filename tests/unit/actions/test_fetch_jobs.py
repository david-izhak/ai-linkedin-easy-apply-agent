import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from core.selectors import selectors

from actions.fetch_jobs import (
    _get_total_job_count, 
    _scrape_page_for_links, 
    fetch_job_links_user, 
    _scrape_job_page_details, 
    _scrape_company_about_page, 
    fetch_job_details
)


class TestGetTotalJobCount:
    
    @pytest.mark.asyncio
    async def test_get_total_job_count_success(self):
        """Test successful retrieval of total job count."""
        mock_page = AsyncMock()
        mock_selector = AsyncMock()
        mock_page.wait_for_selector.return_value = mock_selector
        mock_selector.inner_text.return_value = "123 jobs"
        
        result = await _get_total_job_count(mock_page, "https://example.com/jobs")
        
        mock_page.goto.assert_called_once_with("https://example.com/jobs", wait_until="load")
        mock_page.wait_for_selector.assert_called_once_with("small.jobs-search-results-list__text", timeout=10000)
        mock_selector.inner_text.assert_called_once()
        assert result == 123
    
    @pytest.mark.asyncio
    async def test_get_total_job_count_no_element(self):
        """Test handling when job count element is not found."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.return_value = None
        
        result = await _get_total_job_count(mock_page, "https://example.com/jobs")
        
        mock_page.goto.assert_called_once_with("https://example.com/jobs", wait_until="load")
        mock_page.wait_for_selector.assert_called_once_with("small.jobs-search-results-list__text", timeout=10000)
        assert result == 0
    
    @pytest.mark.asyncio
    async def test_get_total_job_count_exception(self):
        """Test handling exception when getting job count."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = Exception("Timeout")
        
        result = await _get_total_job_count(mock_page, "https://example.com/jobs")
        
        mock_page.goto.assert_called_once_with("https://example.com/jobs", wait_until="load")
        mock_page.wait_for_selector.assert_called_once_with("small.jobs-search-results-list__text", timeout=10000)
        assert result == 0


class TestScrapePageForLinks:
    
    @pytest.mark.asyncio
    async def test_scrape_page_for_links_success(self):
        """Test successful scraping of job links from a page."""
        mock_page = AsyncMock()
        mock_listing1 = AsyncMock()
        mock_listing2 = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_listing1, mock_listing2]
        
        # Mock job card container
        mock_job_card1 = AsyncMock()
        mock_job_card2 = AsyncMock()
        mock_listing1.query_selector.side_effect = [mock_job_card1, AsyncMock(), AsyncMock()]
        mock_listing2.query_selector.side_effect = [mock_job_card2, AsyncMock(), AsyncMock()]
        
        mock_job_card1.get_attribute.return_value = "123"
        mock_job_card2.get_attribute.return_value = "456"
        
        # Mock link elements
        mock_link1 = AsyncMock()
        mock_link2 = AsyncMock()
        mock_listing1.query_selector.side_effect = [
            mock_job_card1,  # job card
            mock_link1,      # link
            AsyncMock()      # company name
        ]
        mock_listing2.query_selector.side_effect = [
            mock_job_card2,  # job card
            mock_link2,      # link
            AsyncMock()      # company name
        ]
        
        mock_link1.get_attribute.return_value = "/jobs/123"
        mock_link1.inner_text.return_value = "Software Engineer"
        
        mock_link2.get_attribute.return_value = "/jobs/456"
        mock_link2.inner_text.return_value = "Data Scientist"
        
        # Mock company name elements
        mock_company1 = AsyncMock()
        mock_company2 = AsyncMock()
        mock_company1.inner_text.return_value = "Company A"
        mock_company2.inner_text.return_value = "Company B"
        
        mock_listing1.query_selector.side_effect = [
            mock_job_card1,  # job card
            mock_link1,      # link
            mock_company1    # company name
        ]
        mock_listing2.query_selector.side_effect = [
            mock_job_card2,  # job card
            mock_link2,      # link
            mock_company2    # company name
        ]
        
        result = await _scrape_page_for_links(mock_page)
        
        mock_page.query_selector_all.assert_called_once_with(".jobs-search-results-list li.jobs-search-results__list-item")
        assert len(result) == 2
        assert result[0] == (123, "/jobs/123", "Software Engineer", "Company A")
        assert result[1] == (456, "/jobs/456", "Data Scientist", "Company B")
    
    @pytest.mark.asyncio
    async def test_scrape_page_for_links_no_listings(self):
        """Test handling when no job listings are found on the page."""
        mock_page = AsyncMock()
        mock_page.query_selector_all.return_value = []
        
        result = await _scrape_page_for_links(mock_page)
        
        mock_page.query_selector_all.assert_called_once_with(".jobs-search-results-list li.jobs-search-results__list-item")
        assert result == []


class TestFetchJobLinksUser:
    
    @pytest.mark.asyncio
    @patch('actions.fetch_jobs._get_total_job_count')
    @patch('actions.fetch_jobs._scrape_page_for_links')
    @patch('actions.fetch_jobs.wait')
    async def test_fetch_job_links_user_success(self, mock_wait, 
                                               mock_scrape_page_for_links, 
                                               mock_get_total_job_count):
        """Test successful fetching of job links."""
        mock_page = AsyncMock()
        mock_get_total_job_count.return_value = 50  # 2 pages of 25 each
        mock_scrape_page_for_links.return_value = [
            (123, "/job1", "Software Engineer", "Company A"),
            (456, "/job2", "Data Scientist", "Company B")
        ]
        
        keywords = "software engineer"
        workplace = {"REMOTE": True, "ON_SITE": False, "HYBRID": True}
        geo_id = "102983012"
        distance = "25"
        f_tpr = "r86400"
        sort_by = "DD"
        
        result = await fetch_job_links_user(mock_page, keywords, workplace, geo_id, distance, f_tpr, sort_by)
        
        mock_get_total_job_count.assert_called_once()
        assert mock_scrape_page_for_links.call_count == 2 # 2 pages
        assert len(result) == 2  # Only unique jobs
        assert result[0] == (123, "/job1", "Software Engineer", "Company A")
        assert result[1] == (456, "/job2", "Data Scientist", "Company B")
    
    @pytest.mark.asyncio
    @patch('actions.fetch_jobs._get_total_job_count')
    async def test_fetch_job_links_user_no_jobs(self, mock_get_total_job_count):
        """Test handling when no jobs are available."""
        mock_page = AsyncMock()
        mock_get_total_job_count.return_value = 0
        
        result = await fetch_job_links_user(mock_page, "software engineer", {}, "102983012", "25", "r86400", "DD")
        
        mock_get_total_job_count.assert_called_once()
        assert result == []


class TestScrapeJobPageDetails:
    
    @pytest.mark.asyncio
    async def test_scrape_job_page_details_success(self):
        """Test successful scraping of job page details."""
        mock_page = AsyncMock()
        
        # Mock description element
        mock_desc_element = AsyncMock()
        mock_page.query_selector.return_value = mock_desc_element
        mock_desc_element.inner_text.return_value = "Job description here"
        
        # For the second call (company description)
        mock_comp_desc_element = AsyncMock()
        mock_page.query_selector.side_effect = [mock_desc_element, mock_comp_desc_element, None]
        mock_comp_desc_element.inner_text.return_value = "Company description here"
        
        # For the third call (criteria elements)
        mock_criteria_element1 = AsyncMock()
        mock_criteria_element2 = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_criteria_element1, mock_criteria_element2]
        
        # Mock header and list elements for criteria
        mock_header1 = AsyncMock()
        mock_list1 = AsyncMock()
        mock_header2 = AsyncMock()
        mock_list2 = AsyncMock()
        
        mock_criteria_element1.query_selector.side_effect = [mock_header1, mock_list1]
        mock_criteria_element2.query_selector.side_effect = [mock_header2, mock_list2]
        
        mock_header1.inner_text.return_value = "Seniority Level"
        mock_list1.inner_text.return_value = "Mid-Senior level"
        mock_header2.inner_text.return_value = "Employment Type"
        mock_list2.inner_text.return_value = "Full-time"
        
        result = await _scrape_job_page_details(mock_page, "/job/123")
        
        assert result["description"] == "Job description here"
        assert result["company_description"] == "Company description here"
        assert result["seniority_level"] == "Mid-Senior level"
        assert result["employment_type"] == "Full-time"


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
            [mock_dd1, mock_dd2, mock_dd3]   # dd elements
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
    @patch('actions.fetch_jobs._scrape_job_page_details')
    @patch('actions.fetch_jobs._scrape_company_about_page')
    async def test_fetch_job_details_success(self, mock_scrape_company_about_page, 
                                           mock_scrape_job_page_details):
        """Test successful fetching of job details."""
        mock_page = AsyncMock()
        job_link = "/jobs/view/1234567890/"
        
        mock_scrape_job_page_details.return_value = {
            "description": "Job description",
            "company_description": "Company description",
            "seniority_level": "Mid-Senior level",
            "employment_type": "Full-time"
        }
        
        mock_scrape_company_about_page.return_value = {
            "company_overview": "Company overview",
            "company_website": "https://company.com",
            "company_industry": "Technology",
            "company_size": "1001-5000 employees"
        }
        
        # Mock company profile link element
        mock_company_profile_link = AsyncMock()
        mock_company_profile_link.get_attribute.return_value = "/company/test-company/"
        mock_page.query_selector.return_value = mock_company_profile_link
        
        result = await fetch_job_details(mock_page, job_link)
        
        mock_page.goto.assert_called_once_with(job_link, wait_until="load")
        mock_page.wait_for_selector.assert_called_once_with("div.jobs-description-content__text", timeout=10000)
        mock_scrape_job_page_details.assert_called_once_with(mock_page, job_link)
        mock_page.query_selector.assert_called_once_with(selectors["company_profile_link"])
        mock_scrape_company_about_page.assert_called_once_with(mock_page, "test-company")
        
        # Check that all details are merged correctly
        assert result["description"] == "Job description"
        assert result["company_description"] == "Company description"
        assert result["seniority_level"] == "Mid-Senior level"
        assert result["employment_type"] == "Full-time"
        assert result["company_overview"] == "Company overview"
        assert result["company_website"] == "https://company.com"
        assert result["company_industry"] == "Technology"
        assert result["company_size"] == "1001-5000 employees"
    
    @pytest.mark.asyncio
    @patch('actions.fetch_jobs._scrape_job_page_details')
    @patch('actions.fetch_jobs._scrape_company_about_page')
    async def test_fetch_job_details_no_company_link(self, mock_scrape_company_about_page, 
                                                   mock_scrape_job_page_details):
        """Test fetching job details when no company link is found."""
        mock_page = AsyncMock()
        job_link = "/jobs/view/1234567890/"
        
        mock_scrape_job_page_details.return_value = {
            "description": "Job description",
            "company_description": "Company description"
        }
        
        mock_page.query_selector.return_value = None  # No company link found
        
        result = await fetch_job_details(mock_page, job_link)
        
        mock_page.goto.assert_called_once_with(job_link, wait_until="load")
        mock_page.wait_for_selector.assert_called_once_with("div.jobs-description-content__text", timeout=10000)
        mock_scrape_job_page_details.assert_called_once_with(mock_page, job_link)
        mock_page.query_selector.assert_called_once_with(selectors["company_profile_link"])
        mock_scrape_company_about_page.assert_not_called()
        
        # Should only have job page details
        assert result["description"] == "Job description"
        assert result["company_description"] == "Company description"
        assert "company_overview" not in result
    
    @pytest.mark.asyncio
    @patch('actions.fetch_jobs._scrape_job_page_details')
    @patch('actions.fetch_jobs._scrape_company_about_page')
    async def test_fetch_job_details_company_link_exception(self, mock_scrape_company_about_page, 
                                                         mock_scrape_job_page_details):
        """Test fetching job details when an exception occurs processing company link."""
        mock_page = AsyncMock()
        job_link = "/jobs/view/1234567890/"
        
        mock_scrape_job_page_details.return_value = {
            "description": "Job description",
            "company_description": "Company description"
        }
        
        mock_page.query_selector.side_effect = Exception("Link not found")
        
        result = await fetch_job_details(mock_page, job_link)
        
        mock_page.goto.assert_called_once_with(job_link, wait_until="load")
        mock_page.wait_for_selector.assert_called_once_with("div.jobs-description-content__text", timeout=10000)
        mock_scrape_job_page_details.assert_called_once_with(mock_page, job_link)
        mock_page.query_selector.assert_called_once_with(selectors["company_profile_link"])
        mock_scrape_company_about_page.assert_not_called()
        
        # Should only have job page details
        assert result["description"] == "Job description"
        assert result["company_description"] == "Company description"
        assert "company_overview" not in result