import asyncio
import sys
import os
import logging
from playwright.async_api import async_playwright

# It's important to set up logging before other imports that might use it.
from core.logger import setup_logging

setup_logging()

from config import (
    BOT_MODE,
    MAX_APPLICATIONS_PER_DAY,
    USER_DATA_DIR,
    BROWSER_HEADLESS,
    LINKEDIN_EMAIL,
    LINKEDIN_PASSWORD,
)
from actions.login import login
from core.database import (
    setup_database,
    count_todays_applications,
    record_run_timestamp,
)
from phases.discovery import run_discovery_phase
from phases.enrichment import run_enrichment_phase
from phases.processing import run_processing_phase

logger = logging.getLogger(__name__)


# --- Main Orchestrator ---
async def main():
    """Main orchestrator function for the LinkedIn Easy Apply bot."""
    logger.info(f"Bot starting in mode: {BOT_MODE}")
    setup_database()

    applications_today_count = count_todays_applications()
    logger.info(f"Applications made today: {applications_today_count}")
    logger.info(f"Daily application limit is set to: {MAX_APPLICATIONS_PER_DAY}")

    if applications_today_count >= MAX_APPLICATIONS_PER_DAY and BOT_MODE in [
        "processing",
        "full_run",
    ]:
        logger.warning(
            "Daily application limit has been reached. Cannot start processing phase. Exiting."
        )
        return

    should_submit = len(sys.argv) > 1 and sys.argv[1] == "SUBMIT"
    logger.info(f"Running in {'SUBMIT' if should_submit else 'DRY RUN'} mode.")

    os.makedirs(USER_DATA_DIR, exist_ok=True)
    successful_run = False

    async with async_playwright() as p:
        logger.info(f"Launching browser with persistent context from: {USER_DATA_DIR}")
        context = await p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=BROWSER_HEADLESS,
            ignore_https_errors=True,
            args=["--disable-setuid-sandbox", "--no-sandbox"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await login(page=page, email=LINKEDIN_EMAIL, password=LINKEDIN_PASSWORD)

        if BOT_MODE in ["discovery", "full_run"]:
            await run_discovery_phase(page)
            successful_run = True

        if BOT_MODE in ["enrichment", "full_run"]:
            await run_enrichment_phase(context)
            successful_run = True

        if BOT_MODE in ["processing", "full_run"]:
            # Pass the global config to the processing phase
            await run_processing_phase(
                context, applications_today_count, should_submit, globals()
            )
            successful_run = True

        logger.info("All phases complete. Closing browser context.")
        await context.close()

    if successful_run:
        record_run_timestamp()
    else:
        logger.warning(
            "Run was not considered successful. Not recording a new run timestamp."
        )


if __name__ == "__main__":
    asyncio.run(main())
