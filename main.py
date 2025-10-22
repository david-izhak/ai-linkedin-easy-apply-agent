import asyncio
import sys
import os
import logging
from playwright.async_api import async_playwright

# It's important to set up logging before other imports that might use it.
from core.logger import setup_logging
from config import config  # Import the new config object

setup_logging()
logger = logging.getLogger(__name__)


def get_submit_mode_from_bot_mode(bot_mode: str) -> bool:
    """
    Determines whether to submit applications based on BOT_MODE.
    
    Args:
        bot_mode: Current bot operating mode
        
    Returns:
        True if mode ends with "_submit", False otherwise
    """
    return bot_mode in ["processing_submit", "full_run_submit"]


def validate_bot_mode(bot_mode: str, valid_modes: list[str]) -> None:
    """
    Validates that the provided BOT_MODE is in the list of valid modes.
    
    Args:
        bot_mode: Current bot operating mode
        valid_modes: List of valid mode strings
        
    Raises:
        ValueError: If bot_mode is not in valid_modes
    """
    if bot_mode not in valid_modes:
        raise ValueError(
            f"Invalid BOT_MODE: '{bot_mode}'. "
            f"Valid modes are: {', '.join(valid_modes)}"
        )


async def run_phase(mode: str, app_config: 'AppConfig', browser_context, applications_today_count: int = 0):
    """Orchestrates the execution of a single bot phase."""
    from phases.discovery import run_discovery_phase
    from phases.enrichment import run_enrichment_phase
    from phases.processing import run_processing_phase

    should_submit = get_submit_mode_from_bot_mode(mode)
    logger.info(f"Running phase '{mode}' in {'SUBMIT' if should_submit else 'DRY RUN'} mode.")

    if mode in ["discovery", "full_run", "full_run_submit"]:
        await run_discovery_phase(app_config=app_config, browser_context=browser_context)

    if mode in ["enrichment", "full_run", "full_run_submit"]:
        await run_enrichment_phase(app_config=app_config, browser_context=browser_context)

    if mode in ["processing", "processing_submit", "full_run", "full_run_submit"]:
        await run_processing_phase(
            context=browser_context,
            applications_today_count=applications_today_count,
            should_submit=should_submit,
            app_config=app_config
        )


# --- Main Orchestrator ---
async def main():
    from actions.login import login
    from core.database import (
        setup_database,
        count_todays_applications,
        record_run_timestamp,
    )

    """Main orchestrator function for the LinkedIn Easy Apply bot."""
    
    # Validate BOT_MODE
    try:
        validate_bot_mode(config.bot_mode.mode, config.bot_mode.valid_modes)
    except ValueError as e:
        logger.error(str(e))
        return
    
    if config.bot_mode.mode == "test_logging":
        logger.info("Logging test mode enabled.")
        logger.debug("This is a debug message.")
        logger.info("This is an info message.")
        logger.warning("This is a warning message.")
        logger.error("This is an error message.")
        logger.critical("This is a critical message.")
        logger.info("Logging test complete. Exiting.")
        return

    logger.info(f"Bot starting in mode: {config.bot_mode.mode}")
    
    db_conn = None
    try:
        db_conn = setup_database(config.session.db_file)
        config.session.db_conn = db_conn  # Set the connection object on the config

        applications_today_count = count_todays_applications(db_conn)
        logger.info(f"Applications made today: {applications_today_count}")
        logger.info(f"Daily application limit is set to: {config.general_settings.max_applications_per_day}")

        if applications_today_count >= config.general_settings.max_applications_per_day and config.bot_mode.mode in [
            "processing", "processing_submit", "full_run", "full_run_submit"
        ]:
            logger.warning("Daily application limit reached. Exiting.")
            return

        os.makedirs(config.session.user_data_dir, exist_ok=True)
        
        async with async_playwright() as p:
            context = None  # Инициализируем context как None
            logger.info(f"Launching browser with persistent context from: {config.session.user_data_dir}")
            context = await p.chromium.launch_persistent_context(
                str(config.session.user_data_dir),
                headless=config.general_settings.browser_headless,
                ignore_https_errors=True,
                args=["--disable-setuid-sandbox", "--no-sandbox"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            await login(page=page)

            await run_phase(config.bot_mode.mode, config, context, applications_today_count)

        record_run_timestamp(db_conn)

    finally:
        if db_conn:
            db_conn.close()
            logger.info("Database connection closed.")


if __name__ == "__main__":
    asyncio.run(main())
