import logging
from playwright.async_api import BrowserContext, Error as PlaywrightError

from config import WAIT_BETWEEN_APPLICATIONS
from core.utils import wait
from actions.fetch_jobs import fetch_job_details
from core.database import get_discovered_jobs, save_enrichment_data, update_job_status

logger = logging.getLogger(__name__)


async def run_enrichment_phase(context: BrowserContext):
    """Runs the enrichment phase: fetching details for discovered jobs."""
    logger.info("--- Starting Enrichment Phase ---")
    jobs_to_enrich = get_discovered_jobs()
    if not jobs_to_enrich:
        logger.info("No discovered jobs to enrich.")
        return

    for i, (job_id, link, title, company_name) in enumerate(jobs_to_enrich):
        logger.info(
            f"Enriching job {i + 1}/{len(jobs_to_enrich)}: {title} (ID: {job_id})"
        )
        enrichment_page = None
        try:
            enrichment_page = await context.new_page()
            details = await fetch_job_details(enrichment_page, link)
            save_enrichment_data(job_id, details)
        except PlaywrightError as e:
            logger.error(
                f"A Playwright error occurred while enriching job ID {job_id}: {e}"
            )
            update_job_status(job_id, "enrichment_error")
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while enriching job ID {job_id}. Exception: {e}",
                exc_info=True,
            )
            update_job_status(job_id, "enrichment_error")
        finally:
            if enrichment_page and not (await enrichment_page.is_closed()):
                await enrichment_page.close()
            wait(WAIT_BETWEEN_APPLICATIONS)
    logger.info("--- Finished Enrichment Phase ---")
