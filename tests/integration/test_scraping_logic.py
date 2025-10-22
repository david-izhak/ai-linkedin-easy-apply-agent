import pytest
from playwright.sync_api import Page
import os

# Removed sys.path.insert as pytest should handle module discovery

from actions.fetch_jobs_sync import _scrape_page_for_links_sync, _scrape_job_page_details_sync, _scrape_company_about_page_sync

# Helper function to load fixture content
def load_fixture(filename):
    fixture_path = os.path.join(os.path.dirname(__file__), '../fixtures', filename)
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return f.read()

class TestScrapingLogic:

    def test_scrape_search_page_for_links(self, page: Page):
        """Tests extracting job links from a saved search results page."""
        html_content = load_fixture('sample_search_page.html')
        page.set_content(html_content)

        scraped_data = _scrape_page_for_links_sync(page)

        assert len(scraped_data) == 2
        # First job
        assert scraped_data[0][0] == 1234567890  # job_id
        assert scraped_data[0][1] == '/jobs/view/1234567890/' # link
        assert scraped_data[0][2] == 'Software Engineer' # title
        assert scraped_data[0][3] == 'Tech Innovations Inc.' # company
        # Second job
        assert scraped_data[1][0] == 987654321 # job_id
        assert scraped_data[1][2] == 'Backend Developer' # title

    def test_scrape_job_page_details(self, page: Page):
        """Tests extracting details from a saved job details page."""
        html_content = load_fixture('sample_job_page.html')
        page.set_content(html_content)

        details = _scrape_job_page_details_sync(page, "/fake-link")

        assert "We are looking for a passionate Software Engineer" in details['description']
        assert "Tech Innovations Inc. is a leader" in details['company_description']
        assert details['seniority_level'] == 'Mid-Senior level'
        assert details['employment_type'] == 'Full-time'
        assert details['industries'] == 'IT Services and IT Consulting'

    def test_scrape_company_about_page(self, page: Page):
        """Tests extracting details from a saved company about page."""
        html_content = load_fixture('sample_company_page.html')
        # The function uses goto, but for this test, set_content is sufficient
        # as we are not testing navigation, just scraping.
        page.set_content(html_content)

        details = _scrape_company_about_page_sync(page, "fake-company-name")

        assert "forward-thinking technology company" in details['company_overview']
        assert details['company_website'] == 'https://tech-innovations.example.com'
        assert details['company_industry'] == 'Software Development'
        assert details['company_size'] == '501-1,000 employees'
