from playwright.async_api import Page
import re
import logging
from urllib.parse import urlencode, urlparse
from core.selectors import selectors
from core.utils import wait

logger = logging.getLogger(__name__)
MAX_PAGE_SIZE = 25


async def _get_total_job_count(page: Page, url: str) -> int:
    """Navigates to the initial search URL and scrapes the total number
    of available jobs."""
    logger.info(f"Navigating to initial search URL to get job count: {url}")
    await page.goto(url, wait_until="load")
    try:
        num_jobs_handle = await page.wait_for_selector(
            selectors["search_result_list_text"], timeout=10000
        )
        if not num_jobs_handle:
            logger.error("Could not find job count element. Aborting search.")
            return 0

        num_available_jobs_text = await num_jobs_handle.inner_text()
        num_available_jobs = int(re.sub(r"\D", "", num_available_jobs_text))
        logger.info(
            f"Found {num_available_jobs} available jobs for the specified criteria."
        )
        return num_available_jobs
    except Exception as e:
        logger.error(
            f"Could not determine the number of available jobs. Exception: {e}",
            exc_info=True,
        )
        return 0


async def _scrape_page_for_links(page: Page) -> list:
    """Scrapes the job_id, link, title, and company from all
    job cards on the currently loaded page."""
    job_listings_data = []
    job_listings = await page.query_selector_all(selectors["search_result_list_item"])

    if not job_listings:
        logger.warning("No job listings found on the current page.")
        return []

    logger.debug(f"Found {len(job_listings)} listings on page.")
    for listing in job_listings:
        try:
            job_card_container = await listing.query_selector(
                selectors["job_card_container"]
            )
            if not job_card_container:
                logger.warning(
                    "Could not find job card container for a listing, skipping."
                )
                continue

            job_id_str = await job_card_container.get_attribute("data-job-id")
            if not job_id_str:
                logger.warning("Could not find job ID for a listing, skipping.")
                continue
            job_id = int(job_id_str)

            link_element = await listing.query_selector(
                selectors["search_result_list_item_link"]
            )
            if not link_element:
                logger.warning("Could not find link element for a listing, skipping.")
                continue

            link_href = await link_element.get_attribute("href")
            if not link_href:
                logger.warning("Link element has no href attribute, skipping.")
                continue

            link = link_href.split("?")[0]
            title = (await link_element.inner_text()).strip()

            company_name_element = await listing.query_selector(
                selectors["search_result_list_item_company_name"]
            )
            company_name = (
                (await company_name_element.inner_text()).strip()
                if company_name_element
                else "Unknown"
            )

            job_listings_data.append((job_id, link, title, company_name))

        except Exception as e:
            logger.warning(
                f"Error processing a job listing link on the search page. Exception: {e}",
                exc_info=True,
            )

    return job_listings_data


async def fetch_job_links_user(
    page: Page,
    keywords: str,
    workplace: dict,
    geo_id: str,
    distance: str,
    f_tpr: str,
    sort_by: str,
) -> list:
    """
    Orchestrates the fetching of basic job information
    by delegating to helper functions.
    """
    f_wt = [
        key
        for key, val in {
            "1": workplace.get("ON_SITE"),
            "2": workplace.get("REMOTE"),
            "3": workplace.get("HYBRID"),
        }.items()
        if val
    ]
    base_url = "https://www.linkedin.com/jobs/search/"

    initial_params = {
        "keywords": keywords,
        "geoId": geo_id,
        "distance": distance,
        "f_TPR": f_tpr,
        "f_WT": ",".join(f_wt),
        "f_AL": "true",
        "sortBy": sort_by,
    }
    initial_url = f"{base_url}?{urlencode(initial_params)}&start=0"

    num_available_jobs = await _get_total_job_count(page, initial_url)
    if num_available_jobs == 0:
        return []

    all_job_listings = []
    num_seen_jobs = 0
    while num_seen_jobs < num_available_jobs:
        search_params = initial_params.copy()
        search_params["start"] = str(num_seen_jobs)
        url = f"{base_url}?{urlencode(search_params)}"
        logger.debug(f"Fetching job links from URL: {url}")

        await page.goto(url, wait_until="load")
        await page.wait_for_selector(
            f"{selectors['search_result_list_item']}:nth-child(1)", timeout=10000
        )

        page_results = await _scrape_page_for_links(page)
        if not page_results:
            logger.warning("Scraping returned no results for a page, breaking loop.")
            break

        all_job_listings.extend(page_results)

        wait(1000)
        num_seen_jobs += MAX_PAGE_SIZE

    unique_jobs = list({job[0]: job for job in all_job_listings}.values())
    logger.info(f"Extracted {len(unique_jobs)} unique job links in total.")
    return unique_jobs


async def _scrape_job_page_details(page: Page, link: str) -> dict:
    """Scrapes details from the main job listing page."""
    details = {}
    try:
        description_element = await page.query_selector(selectors["job_description"])
        if description_element:
            details["description"] = await description_element.inner_text()
    except Exception as e:
        logger.warning(
            f"Could not fetch job description for {link}. Exception: {e}", exc_info=True
        )

    try:
        company_description_element = await page.query_selector(
            selectors["company_description"]
        )
        if company_description_element:
            details["company_description"] = (
                await company_description_element.inner_text()
            )
    except Exception as e:
        logger.warning(
            f"Could not fetch company description on job page for {link}. Exception: {e}",
            exc_info=True,
        )

    try:
        criteria_elements = await page.query_selector_all(
            selectors["job_criteria_list"]
        )
        for element in criteria_elements:
            header_element = await element.query_selector("h3")
            list_items_element = await element.query_selector("ul")
            if header_element and list_items_element:
                header_text = (await header_element.inner_text()).strip().lower()
                list_items_text = (await list_items_element.inner_text()).strip()
                key_map = {
                    "seniority level": "seniority_level",
                    "employment type": "employment_type",
                    "job function": "job_function",
                    "industries": "industries",
                }
                if header_text in key_map:
                    details[key_map[header_text]] = list_items_text
    except Exception as e:
        logger.warning(
            f"Could not fetch all job criteria for {link}. Exception: {e}",
            exc_info=True,
        )
    return details


async def _scrape_company_about_page(page: Page, company_name: str) -> dict:
    """Scrapes details from the company's 'About' page."""
    details = {}
    about_url = f"https://www.linkedin.com/company/{company_name}/about/"
    logger.info(f"Navigating to company 'About' page: {about_url}")
    await page.goto(about_url, wait_until="load")

    try:
        overview_el = await page.query_selector(selectors["company_about_overview"])
        if overview_el:
            details["company_overview"] = await overview_el.inner_text()
    except Exception as e:
        logger.warning(
            f"Could not fetch company overview for {company_name}. Exception: {e}",
            exc_info=True,
        )

    try:
        details_list = await page.query_selector(
            selectors["company_about_details_list"]
        )
        if details_list:
            dt_elements = await details_list.query_selector_all("dt")
            dd_elements = await details_list.query_selector_all("dd")
            for i in range(len(dt_elements)):
                term = (await dt_elements[i].inner_text()).strip().lower()
                definition = (await dd_elements[i].inner_text()).strip()
                if term == "website":
                    details["company_website"] = definition
                elif term == "industry":
                    details["company_industry"] = definition
                elif term == "company size":
                    details["company_size"] = definition
    except Exception as e:
        logger.warning(
            f"Could not fetch company details list for {company_name}. Exception: {e}",
            exc_info=True,
        )
    return details


async def fetch_job_details(page: Page, link: str) -> dict:
    """
    Orchestrates scraping of job and company details.
    """
    logger.debug(f"Fetching all details for job page: {link}")
    await page.goto(link, wait_until="load")
    await page.wait_for_selector(selectors["job_description"], timeout=10000)

    # Scrape details from the job page itself
    job_page_details = await _scrape_job_page_details(page, link)

    # Scrape details from the company's about page
    company_about_details = {}
    try:
        company_profile_link_element = await page.query_selector(
            selectors["company_profile_link"]
        )
        if company_profile_link_element:
            company_href = await company_profile_link_element.get_attribute("href")
            if company_href:
                path_parts = urlparse(company_href).path.strip("/").split("/")
                if path_parts[0] == "company":
                    company_name = path_parts[1]
                    company_about_details = await _scrape_company_about_page(
                        page, company_name
                    )
        else:
            logger.warning(f"Could not find company profile link on job page {link}")
    except Exception as e:
        logger.error(
            f"Failed to process company 'About' page for job {link}. Exception: {e}",
            exc_info=True,
        )

    # Merge all details into one dictionary
    all_details = {**job_page_details, **company_about_details}
    logger.debug(f"Finished fetching all details for job {link}")
    return all_details
