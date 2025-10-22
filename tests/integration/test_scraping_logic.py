import pytest
from playwright.async_api import Page, Route
import os
from actions.fetch_jobs import _extract_job_data_from_page, fetch_job_details


def load_fixture(filename):
    fixture_path = os.path.join(os.path.dirname(__file__), "../fixtures", filename)
    with open(fixture_path, "r", encoding="utf-8") as f:
        return f.read()


class TestScrapingLogic:

    @pytest.mark.asyncio
    async def test_scrape_search_page_for_links(self, page: Page):
        """Tests extracting job links from a saved search results page."""
        html_content = load_fixture("sample_search_page.html")
        await page.set_content(html_content)
        scraped_data = await _extract_job_data_from_page(page)
        assert len(scraped_data) == 2
        assert scraped_data[0][0] == 1234567890
        assert scraped_data[0][1] == "/jobs/view/1234567890"
        assert scraped_data[0][2] == "Software Engineer"
        assert scraped_data[0][3] == "Tech Innovations Inc."
        assert scraped_data[1][0] == 987654321
        assert scraped_data[1][1] == "/jobs/view/0987654321"
        assert scraped_data[1][2] == "Backend Developer"
        assert scraped_data[1][3] == "Data Systems LLC"

    @pytest.mark.asyncio
    async def test_fetch_job_details(self, page: Page):
        """
        Tests extracting details from a job page and its associated company page.
        This test mocks the navigation to both pages.
        """
        job_page_html = load_fixture("sample_job_page.html")
        company_page_html = load_fixture("sample_company_page.html")

        job_url = "https://www.linkedin.com/jobs/view/12345"
        company_url = "https://www.linkedin.com/company/tech-innovations-inc/about/"

        async def handle_route(route: Route):
            request_url = route.request.url
            if request_url == job_url:
                await route.fulfill(body=job_page_html, content_type="text/html")
            elif request_url.startswith(company_url):
                await route.fulfill(body=company_page_html, content_type="text/html")
            else:
                await route.continue_()

        await page.route("**/*", handle_route)

        details = await fetch_job_details(page, job_url)

        # Assertions for job page details
        assert "We are looking for a passionate Software Engineer" in details.get(
            "description", ""
        )
        assert "Tech Innovations Inc. is a leader" in details.get(
            "company_description", ""
        )
        assert details.get("seniority_level") == "Mid-Senior level"
        assert details.get("employment_type") == "Full-time"
        assert details.get("industries") == "IT Services and IT Consulting"

        # Assertions for company about page details
        assert "forward-thinking technology company" in details.get(
            "company_overview", ""
        )
        assert details.get("company_website") == "https://tech-innovations.example.com"
        assert details.get("company_industry") == "Software Development"
        assert details.get("company_size") == "501-1,000 employees"
