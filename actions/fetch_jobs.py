from playwright.async_api import Page
import re
import logging
from urllib.parse import urlencode
from core.selectors import selectors
from core.utils import (
    make_search_key,
    wait_for_any_selector,
    construct_full_url,
)
from config import config  # Import new config object
from core import database
from core import resilience
import sqlite3
from config import AppConfig

logger = logging.getLogger(__name__)
MAX_PAGE_SIZE = 25


async def _ensure_all_jobs_are_loaded(page: Page) -> None:
    """
    Прокручивает страницу, чтобы заставить ее загрузить все вакансии,
    используя итерацию по всем элементам списка.
    """
    logger.info("Scrolling through all list items to ensure they are loaded...")

    # list_item_selector = ".scaffold-layout__list-item"
    list_item_selector = selectors["job_card_container_in_list"]
    try:
        await page.wait_for_selector(list_item_selector, timeout=config.performance.max_wait_ms)
        list_items = await page.query_selector_all(list_item_selector)

        logger.info(f"Found {len(list_items)} list items to scroll through.")

        for i, item in enumerate(list_items):
            try:
                await item.scroll_into_view_if_needed()
                logger.debug(f"Scrolled to item {i + 1}/{len(list_items)}")
                await page.wait_for_timeout(200)  # Небольшая пауза после каждой прокрутки
            except Exception as e:
                logger.warning(f"Could not scroll to item {i + 1}. It might have been removed from DOM. Error: {e}")

        # Дополнительная прокрутка до конца на случай, если есть кнопка "Показать еще"
        job_list_container = page.locator("div.jobs-search-results-list, div.scaffold-layout__list").first
        if await job_list_container.is_visible():
            await job_list_container.evaluate("element => element.scrollTop = element.scrollHeight")
            await page.wait_for_timeout(1000)

        show_more_button_selector = selectors["show_more_button"]
        if await page.is_visible(show_more_button_selector, timeout=1000):
            logger.info("'Show more' button found after scrolling. Clicking it...")
            await page.click(show_more_button_selector)
            await page.wait_for_timeout(2000) # Даем время на загрузку

    except Exception as e:
        logger.error(f"An error occurred during the scrolling process: {e}")

    logger.info("Finished scrolling through list items.")


def fetch_job_links_limit() -> int | None:
    """Get the maximum number of jobs to fetch from config."""
    return config.job_limits.max_jobs_to_discover


async def _get_total_job_count(page: Page, url: str) -> int:
    """Gets the total number of jobs from the search results page."""
    # More robust selectors to find the job count
    job_count_selectors = [
        ".jobs-search-results-list__subtitle span[dir='ltr']",
        'small.jobs-search-results-list__text',
        '.results-context-header__job-count',
    ]
    executor = resilience.get_selector_executor(page)

    for selector in job_count_selectors:
        try:
            # Use a short timeout for each attempt
            result = await executor.get_text(selector, timeout=2000)
            if result:
                # Extract numbers from the text
                count_text = re.search(r"(\d{1,3}(,\d{3})*|\d+)", result)
                if count_text:
                    return int(count_text.group(0).replace(",", ""))
        except Exception:
            logger.debug(
                f"Could not find job count with selector '{selector}', trying next.",
                exc_info=True
            )
            continue

    logger.warning(
        f"Could not extract total job count from page {url} with any selector, falling back to counting cards."
    )

    # Fallback if selectors fail or text parsing fails
    try:
        job_cards = await page.query_selector_all('div.job-card-container[data-job-id]')
        return len(job_cards)
    except Exception as e:
        logger.error(f"Fallback to counting job cards failed. Error: {e}")
        return 0


async def _extract_job_data_from_page(page: Page) -> list:
    """
    Scrapes the job_id, link, title, and company from all
    job cards on the currently loaded page using a simplified and direct approach.
    """
    job_listings_data = []
    # list_item_selector = ".scaffold-layout__list-item"
    list_item_selector = selectors["job_card_container_in_list"]

    logger.info(f"Scraping job links using selector: '{list_item_selector}'")
    job_listings = await page.query_selector_all(list_item_selector)

    if not job_listings:
        logger.warning("No job listings found on the current page with the specified selector.")
        return []

    logger.info(f"Found {len(job_listings)} job list items to process.")

    for listing in job_listings:
        try:
            job_id_str = await listing.get_attribute("data-occludable-job-id")
            if not job_id_str or not job_id_str.strip():
                logger.debug("Skipping list item as it has no 'data-occludable-job-id'. It might be a placeholder or ad.")
                continue
            
            job_id = int(job_id_str)

            link_element = await listing.query_selector("a.job-card-container__link")
            title_element = await listing.query_selector("a.job-card-container__link strong")
            company_element = await listing.query_selector("div.artdeco-entity-lockup__subtitle span")

            if not all([link_element, title_element, company_element]):
                logger.warning(f"Could not find all required elements for job ID {job_id}. Skipping.")
                continue

            link_href = await link_element.get_attribute("href")
            if not link_href:
                logger.warning(f"Link element has no href for job ID {job_id}. Skipping.")
                continue

            link = link_href.split("?")[0]
            title = (await title_element.inner_text()).strip()
            company_name = (await company_element.inner_text()).strip()

            job_listings_data.append((job_id, link, title, company_name))

        except Exception as e:
            logger.error(
                f"Error processing a job listing item. Exception: {e}",
                exc_info=True,
            )

    logger.info(f"Successfully scraped {len(job_listings_data)} job links from the page.")
    return job_listings_data


async def fetch_job_links_user(
    page: Page, app_config: AppConfig, db_conn: sqlite3.Connection
) -> list:
    """Fetches job links from the LinkedIn job search page.

    Args:
        page: The Playwright page object.
        app_config: The application configuration object.
        db_conn: The database connection object.

    Returns:
        A list of tuples, where each tuple contains job_id, link, title, and company.
    """
    max_jobs_to_fetch = fetch_job_links_limit()
    if max_jobs_to_fetch == 0:
        logger.info("max_jobs_to_discover is set to 0. Skipping job discovery.")
        return []

    logger.info("Navigating to job search page to begin discovery...")
    
    # Calculate f_tpr from config
    job_search_period = app_config.job_search.job_search_period_seconds
    f_tpr = f"r{job_search_period}"

    # Mapping for workplace types from boolean config to LinkedIn filter values
    # Note: LinkedIn uses numeric codes for these filters.
    workplace_mapping = {
        "1": app_config.workplace.on_site,
        "2": app_config.workplace.remote,
        "3": app_config.workplace.hybrid,
    }

    # Construct the f_WT parameter string from the workplace_mapping
    # e.g. "2" for remote, "1,2" for on_site and remote
    f_wt = [
        key
        for key, val in workplace_mapping.items()
        if val
    ]
    base_url = "https://www.linkedin.com/jobs/search/"

    initial_params = {
        "keywords": app_config.job_search.keywords,
        "geoId": app_config.job_search.geo_id,
        "distance": app_config.job_search.distance,
        "f_TPR": f_tpr,
        "f_WT": ",".join(f_wt),
        "f_AL": "true",
        "sortBy": app_config.job_search.sort_by,
    }
    initial_url = f"{base_url}?{urlencode(initial_params)}&start=0"

    # Build deterministic search key for discovery state
    search_key = make_search_key(initial_params)
    state = database.get_discovery_state(search_key, db_conn)
    if state:
        logger.info(
            f"Loaded discovery state for key={search_key[:8]}... max_id={state.get('last_seen_max_job_id')} sweep_before={state.get('last_complete_sweep_before_id')}"
        )

    logger.info(f"Navigating to initial search URL: {initial_url}")
    await page.goto(initial_url, wait_until="load")

    num_available_jobs = await _get_total_job_count(page, initial_url)
    if num_available_jobs == 0:
        return []

    unseen_collected = []
    observed_ids_this_run: list[int] = []

    if max_jobs_to_fetch and max_jobs_to_fetch < num_available_jobs:
        logger.info(
            f"Limiting job discovery to {max_jobs_to_fetch} jobs (out of {num_available_jobs} available)"
        )

    # Compile JOB_TITLE regex pattern once before the loop for performance
    job_title_pattern = re.compile(config.job_search.job_title_regex, re.IGNORECASE)
    logger.debug(f"Using JOB_TITLE filter pattern: {config.job_search.job_title_regex}")

    while True:
        # Вызываем скроллинг здесь, чтобы подгрузить все вакансии на текущей странице
        await _ensure_all_jobs_are_loaded(page)

        # Wait for any job listing to appear (robust to DOM variations)
        # Use optimized parallel selector waiting instead of networkidle + polling
        logger.debug("Waiting for job listings to appear...")
        
        listing_selectors = [
            # selectors['search_result_list_item'],
            # selectors['search_result_list_item_guest'],
            selectors['job_card_container']
        ]
        
        result = await wait_for_any_selector(
            page,
            listing_selectors,
            timeout=config.performance.max_wait_ms
        )
        
        if not result:
            logger.error("Timeout waiting for job listings")
            # Continue anyway - let scraping function handle empty results
        else:
            matched_selector, _ = result
            logger.debug(f"Found job listings with selector: {matched_selector}")

        page_results = await _extract_job_data_from_page(page)
        if not page_results:
            logger.warning("Scraping returned no results for a page, breaking loop.")
            break

        # Track observed ids for watermark sweep boundary
        observed_ids_this_run.extend([jid for jid, *_ in page_results])

        # Filter out already existing vacancies to accumulate only unseen
        candidate_ids = [jid for jid, *_ in page_results]
        existing_ids = database.get_existing_vacancy_ids(candidate_ids, db_conn)
        page_unseen = [job for job in page_results if job[0] not in existing_ids]

        # Filter by JOB_TITLE regex pattern
        page_title_filtered = []
        for job in page_unseen:
            job_id, link, title, company_name = job
            if job_title_pattern.search(title):
                page_title_filtered.append(job)
            else:
                logger.debug(f"Filtered out '{title}' - doesn't match JOB_TITLE pattern")
        
        # Log filtering statistics for this page
        if page_unseen:
            filtered_count = len(page_unseen) - len(page_title_filtered)
            logger.info(
                f"Title filter: {len(page_title_filtered)}/{len(page_unseen)} jobs accepted, "
                f"{filtered_count} filtered out"
            )

        # Accumulate filtered jobs until we reach the configured limit
        for job in page_title_filtered:
            if max_jobs_to_fetch and len(unseen_collected) >= max_jobs_to_fetch:
                break
            unseen_collected.append(job)

        if max_jobs_to_fetch and len(unseen_collected) >= max_jobs_to_fetch:
            logger.info(
                f"Reached configured limit of {max_jobs_to_fetch} unseen jobs. Stopping discovery."
            )
            break

        # Check for and click the 'Next' pagination button
        next_button_selector = "button.jobs-search-pagination__button--next"
        if await page.is_visible(next_button_selector, timeout=2000):
            logger.info("Found 'Next' pagination button. Clicking it...")
            await page.click(next_button_selector)
            await page.wait_for_timeout(2000) # Give some time for the next page to load
            # After clicking next, we need to continue the loop to process the new page
        else:
            logger.info("No 'Next' pagination button found. Reached the end of pagination.")
            break # Break the loop if no next button

    # Persist newly discovered unseen jobs
    if unseen_collected:
        database.save_discovered_jobs(unseen_collected, db_conn)

    # Update discovery state watermarks
    last_seen_max_job_id = None
    if unseen_collected:
        last_seen_max_job_id = max(job[0] for job in unseen_collected)
    last_complete_sweep_before_id = None
    if observed_ids_this_run:
        last_complete_sweep_before_id = min(observed_ids_this_run)

    database.upsert_discovery_state(
        search_key=search_key,
        last_seen_max_job_id=last_seen_max_job_id,
        last_complete_sweep_before_id=last_complete_sweep_before_id,
        conn=db_conn,
    )

    unique_jobs = list({job[0]: job for job in unseen_collected}.values())
    logger.info(
        f"Extracted {len(unique_jobs)} unique new job links in total (observed ids this run: {len(observed_ids_this_run)})."
    )
    return unique_jobs


async def _scrape_job_page_details(page: Page, link: str) -> dict:
    """Scrapes details from the main job listing page."""
    logger.debug(f"Scraping job details for {link}...")
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
            description_text = await company_description_element.inner_text()
            details["company_description"] = description_text
            logger.debug(f"Found company description: {description_text[:100]}...")
        else:
            logger.debug("Company description selector did not find any element.")
    except Exception as e:
        logger.warning(
            f"Could not fetch company description on job page for {link}. Exception: {e}",
            exc_info=True,
        )

    try:
        criteria_elements = await page.query_selector_all(
            selectors["job_criteria_list"]
        )
        logger.debug(f"Found {len(criteria_elements)} job criteria elements. criteria_elements: {criteria_elements}")
        for element in criteria_elements:
            header_element = await element.query_selector("h3")
            list_items_element = await element.query_selector("ul")
            if header_element and list_items_element:
                header_text = (await header_element.inner_text()).strip().lower()
                logger.debug(f"Found job criteria header: {header_text}")
                list_items_text = (await list_items_element.inner_text()).strip()
                logger.debug(f"Found job criteria list items: {list_items_text}")
                key_map = {
                    "seniority level": "seniority_level",
                    "employment type": "employment_type",
                    "job function": "job_function",
                    "industries": "industries",
                }
                logger.debug(f"Found job criteria keys: {key_map}")
                if header_text in key_map:
                    details[key_map[header_text]] = list_items_text
    except Exception as e:
        logger.warning(
            f"Could not fetch all job criteria for {link}. Exception: {e}",
            exc_info=True,
        )
    return details


async def _scrape_company_about_page(page: Page, about_url: str) -> dict:
    """Scrapes details from the company's 'About' page."""
    details = {}
    logger.info(f"Navigating to company 'About' page: {about_url}")
    await page.goto(about_url, wait_until="load")

    try:
        overview_el = await page.query_selector(selectors["company_about_overview"])
        if overview_el:
            details["company_overview"] = await overview_el.inner_text()
    except Exception as e:
        logger.warning(
            f"Could not fetch company overview. Exception: {e}",
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
            f"Could not fetch company details list. Exception: {e}",
            exc_info=True,
        )
    return details


async def fetch_job_details(page: Page, link: str) -> dict:
    """Fetches all details for a given job posting."""
    logger.debug(f"Fetching all details for job page: {link}")

    full_link = construct_full_url(link)

    await page.goto(full_link, wait_until="load")

    details = await _scrape_job_page_details(page, full_link)

    # Scrape details from the company's about page
    company_about_details = {}
    try:
        company_profile_link_element = await page.query_selector(
            selectors["company_profile_link"]
        )
        if company_profile_link_element:
            company_href = await company_profile_link_element.get_attribute("href")
            if company_href:
                about_url = construct_full_url(company_href).replace("/life", "/about/")
                company_about_details = await _scrape_company_about_page(
                    page, about_url
                )
        else:
            logger.warning(f"Could not find company profile link on job page {link}")
    except Exception as e:
        logger.error(
            f"Failed to process company 'About' page for job {link}. Exception: {e}",
            exc_info=True,
        )

    # Merge all details into one dictionary
    all_details = {**details, **company_about_details}
    logger.debug(f"Finished fetching all details for job {link}")
    return all_details
