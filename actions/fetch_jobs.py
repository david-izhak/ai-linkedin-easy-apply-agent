import asyncio
from playwright.async_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
import re
import logging
from urllib.parse import urlencode
from core.selectors import selectors
from core.utils import (
    wait_for_any_selector,
    construct_full_url,
)
from config import config  # Import new config object
from core import database
from core import resilience
import sqlite3
from config import AppConfig

logger = logging.getLogger(__name__)

DEFAULT_TEXT_RETRY_DELAYS = (3, 6, 9)
DEFAULT_TEXT_RETRY_LABEL = "/".join(str(delay) for delay in DEFAULT_TEXT_RETRY_DELAYS)


async def _extract_text_with_retry(locator, label: str, delays=DEFAULT_TEXT_RETRY_DELAYS):
    """Scrolls to the locator and attempts to retrieve non-empty text with retries."""
    delay_sequence_label = "/".join(str(delay) for delay in delays)
    for delay in delays:
        try:
            await locator.scroll_into_view_if_needed()
        except PlaywrightError as scroll_error:
            logger.debug(
                "%s locator not ready for scrolling (delay %s): %s",
                label,
                delay,
                scroll_error,
            )
            await asyncio.sleep(0.5)
            continue

        await asyncio.sleep(delay)

        try:
            text = (await locator.inner_text()).strip()
        except PlaywrightError as read_error:
            logger.debug(
                "Failed to read %s text (delay %s): %s",
                label,
                delay,
                read_error,
            )
            continue

        if text:
            return text

        logger.debug(
            "%s still empty after waiting %s seconds.",
            label,
            delay,
        )

    raise TimeoutError(
        f"{label} text did not load after waiting {delay_sequence_label} seconds."
    )


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
    logger.info(f"Navigating to initial search URL: {initial_url}")
    await page.goto(initial_url, wait_until="load")

    num_available_jobs = await _get_total_job_count(page, initial_url)
    if num_available_jobs == 0:
        return []

    unseen_collected = []

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

    unique_jobs = list({job[0]: job for job in unseen_collected}.values())
    logger.info(
        f"Extracted {len(unique_jobs)} unique new job links in total."
    )
    return unique_jobs


async def _scrape_job_page_details(page: Page, link: str) -> dict:
    """Scrapes details from the main job listing page."""
    logger.debug(f"Scraping job details for {link}...")
    details = {}
    description_element_selector = selectors["job_description"]
    logger.debug(f"For description_element from job page using selector: {description_element_selector}")
    description_locator = page.locator(description_element_selector).first
    description_locator_ready = True
    try:
        await description_locator.wait_for(
            state="attached",
            timeout=config.performance.max_wait_ms,
        )
        await description_locator.wait_for(
            state="visible",
            timeout=config.performance.max_wait_ms,
        )
    except PlaywrightTimeoutError:
        logger.warning(
            "Job description locator `%s` did not become ready within %s ms.",
            description_element_selector,
            config.performance.max_wait_ms,
        )
        description_locator_ready = False

    if description_locator_ready:
        try:
            description_text = await _extract_text_with_retry(
                description_locator,
                "Job description",
            )
            details["description"] = description_text
            logger.debug(f"Found job description: {description_text[:100]}...")
        except TimeoutError:
            logger.error("Timed out waiting for non-empty job description text.")
            raise
        except Exception as e:
            logger.warning(
                f"Could not fetch job description for {link}. Exception: {e}",
                exc_info=True,
            )
    else:
        logger.warning(
            "Job description selector did not find any element. Selector: %s",
            description_element_selector,
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
            logger.warning(f"Company description selector did not find any element. Selector: {description_element_selector}")
    except Exception as e:
        logger.warning(
            f"Could not fetch company description on job page for {link}. Exception: {e}",
            exc_info=True,
        )

    try:
        employment_type_elements = await page.query_selector_all(
            selectors["employment_type_details"]
        )
        if employment_type_elements:
            employment_types = [
                await el.inner_text() for el in employment_type_elements
            ]
            details["employment_type"] = ", ".join(employment_types[:2])
            logger.debug(f"Found employment type: {details['employment_type']}")
        else:
            logger.warning(f"Employment type selector did not find any elements. Selector: {selectors['employment_type_details']}")
    except Exception as e:
        logger.warning(
            f"Could not fetch employment type for {link}. Exception: {e}",
            exc_info=True,
        )
        
    return details


async def _scrape_company_about_page(page: Page, about_url: str) -> dict:
    """Scrapes details from the company's 'About' page."""
    details = {}
    logger.info(f"Navigating to company 'About' page: {about_url}")
    await page.goto(about_url, wait_until="load")

    overview_selector = selectors["company_about_overview"]
    overview_locator = page.locator(overview_selector).first
    overview_ready = True
    try:
        await overview_locator.wait_for(
            state="attached",
            timeout=config.performance.max_wait_ms,
        )
        await overview_locator.wait_for(
            state="visible",
            timeout=config.performance.max_wait_ms,
        )
    except PlaywrightTimeoutError:
        logger.warning(
            "Company overview locator `%s` did not become ready within %s ms.",
            overview_selector,
            config.performance.max_wait_ms,
        )
        overview_ready = False

    if overview_ready:
        try:
            overview_text = await _extract_text_with_retry(
                overview_locator,
                "Company overview",
            )
            details["company_overview"] = overview_text
            logger.debug(f"Found company overview: {overview_text[:100]}...")
        except TimeoutError:
            logger.warning(
                "Timed out waiting for company overview text after %s seconds.",
                DEFAULT_TEXT_RETRY_LABEL,
            )
        except Exception as e:
            logger.warning(
                f"Could not fetch company overview. Exception: {e}",
                exc_info=True,
            )
    else:
        logger.warning(
            "Company overview selector did not find any element. Selector: %s",
            overview_selector,
        )

    details_list_selector = selectors["company_about_details_list"]
    details_list_locator = page.locator(details_list_selector).first
    details_list_ready = True
    try:
        await details_list_locator.wait_for(
            state="attached",
            timeout=config.performance.max_wait_ms,
        )
    except PlaywrightTimeoutError:
        logger.warning(
            "Company details list locator `%s` did not attach within %s ms.",
            details_list_selector,
            config.performance.max_wait_ms,
        )
        details_list_ready = False

    if details_list_ready:
        try:
            try:
                await details_list_locator.scroll_into_view_if_needed()
            except PlaywrightError as scroll_error:
                logger.debug(
                    "Company details list not ready for scrolling: %s",
                    scroll_error,
                )

            detail_pairs = []
            for delay in DEFAULT_TEXT_RETRY_DELAYS:
                await asyncio.sleep(delay)
                try:
                    evaluation_result = await details_list_locator.evaluate(
                        """(node) => {
                            const dts = Array.from(node.querySelectorAll('dt'));
                            const dds = Array.from(node.querySelectorAll('dd'));
                            const pairs = [];
                            const limit = Math.min(dts.length, dds.length);
                            for (let i = 0; i < limit; i += 1) {
                                const term = dts[i].innerText.trim().toLowerCase();
                                const definition = dds[i].innerText.trim();
                                if (term && definition) {
                                    pairs.push([term, definition]);
                                }
                            }
                            return pairs;
                        }"""
                    )
                except PlaywrightError as eval_error:
                    logger.debug(
                        "Failed to evaluate company details list (delay %s): %s",
                        delay,
                        eval_error,
                    )
                    continue

                detail_pairs = evaluation_result or []
                if detail_pairs:
                    break

                logger.debug(
                    "Company details list still empty after waiting %s seconds.",
                    delay,
                )

            if detail_pairs:
                for term, definition in detail_pairs:
                    if term == "website":
                        details["company_website"] = definition
                        logger.debug(f"Found company website: {definition}")
                    elif term == "industry":
                        details["company_industry"] = definition
                        logger.debug(f"Found company industry: {definition}")
                    elif term == "company size":
                        details["company_size"] = definition
                        logger.debug(f"Found company size: {definition}")
            else:
                logger.warning(
                    "Company details list did not load after waiting %s seconds.",
                    DEFAULT_TEXT_RETRY_LABEL,
                )
        except Exception as e:
            logger.warning(
                f"Could not fetch company details list. Exception: {e}",
                exc_info=True,
            )
    else:
        logger.warning(
            "Company details list selector did not find any element. Selector: %s",
            details_list_selector,
        )

    return details


async def fetch_job_details(page: Page, link: str, noncritical_error_tracker: dict | None = None) -> dict:
    """Fetches all details for a given job posting.
    
    Raises:
        Exception: If a critical error occurs during fetching (e.g., TimeoutError
                   when navigating to company page). Non-critical errors (e.g., 
                   missing company profile link) are logged but don't raise exceptions.
    """
    logger.debug(f"Fetching all details for job page: {link}")

    full_link = construct_full_url(link)

    await page.goto(full_link, wait_until="load")

    details = await _scrape_job_page_details(page, full_link)

    # Scrape details from the company's about page
    company_about_details = {}
    try:
        try:
            company_profile_link_element = await page.query_selector(
                selectors["company_profile_link"]
            )
        except Exception as e:
            # Non-critical: if we can't find the company link selector, just log and continue
            logger.warning(
                f"Could not query selector for company profile link on job page {link}. "
                f"Exception: {e}. Continuing without company about details."
            )
            if noncritical_error_tracker is not None:
                noncritical_error_tracker["company_link_query"] = noncritical_error_tracker.get("company_link_query", 0) + 1
                logger.warning(
                    "Noncritical error: company_link_query (%s). URL %s",
                    noncritical_error_tracker["company_link_query"],
                    link,
                )
            company_profile_link_element = None
        
        if company_profile_link_element:
            if noncritical_error_tracker is not None and noncritical_error_tracker.get("company_link_query", 0) > 0:
                noncritical_error_tracker["company_link_query"] = 0
                logger.debug("Recovered: company_link_query reset to 0")
            company_href = await company_profile_link_element.get_attribute("href")
            if company_href:
                about_url = construct_full_url(company_href).replace("/life", "/about")
                try:
                    company_about_details = await _scrape_company_about_page(
                        page, about_url
                    )
                    if noncritical_error_tracker is not None and noncritical_error_tracker.get("company_about_scrape", 0) > 0:
                        noncritical_error_tracker["company_about_scrape"] = 0
                        logger.debug("Recovered: company_about_scrape reset to 0")
                except Exception as e:
                    # Check if this is a critical error (like TimeoutError)
                    # that indicates a failure to fetch required data
                    if isinstance(e, (TimeoutError, ConnectionError)):
                        logger.error(
                            f"Critical error occurred while scraping company 'About' page "
                            f"for job {link}. Exception: {e}",
                            exc_info=True,
                        )
                        raise
                    else:
                        # Non-critical error: log and continue without company about details
                        logger.warning(
                            f"Failed to scrape company 'About' page for job {link}. "
                            f"Exception: {e}. Continuing without company about details."
                        )
                        if noncritical_error_tracker is not None:
                            noncritical_error_tracker["company_about_scrape"] = noncritical_error_tracker.get("company_about_scrape", 0) + 1
                            logger.warning(
                                "Noncritical error: company_about_scrape (%s). URL %s",
                                noncritical_error_tracker["company_about_scrape"],
                                link,
                            )
        else:
            logger.warning(f"Could not find company profile link on job page {link}")
    except (TimeoutError, ConnectionError):
        # Re-raise critical errors that indicate a failure to fetch required data
        raise
    except Exception as e:
        # This should not happen, but if it does, log and continue
        logger.warning(
            f"Unexpected error while processing company details for job {link}. "
            f"Exception: {e}. Continuing without company about details.",
            exc_info=True,
        )

    # Merge all details into one dictionary
    all_details = {**details, **company_about_details}
    logger.debug(f"Finished fetching all details for job {link}")
    return all_details
