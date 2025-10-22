"""
Example usage of ModalFlowRunner with LLM integration.

This demonstrates how to use the modal flow engine with LLM delegate for fallback decisions.
"""

import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from modal_flow.modal_flow import ModalFlowRunner
from modal_flow.profile_store import ProfileStore
from modal_flow.rules_store import RuleStore
from modal_flow.normalizer import QuestionNormalizer
from modal_flow.llm_delegate_openai import OpenAILLMDelegate

# Import LLM client factory
from llm.client_factory import get_llm_client
from config import LLMSettings


async def main():
    """Example main function with LLM integration."""
    # Setup logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    
    # Load profile
    profile_path = Path("config/profile_example.json")
    if not profile_path.exists():
        logger.error(f"Profile file not found: {profile_path}")
        return
    
    profile_store = ProfileStore(profile_path)
    profile = profile_store.load()
    logger.info("Profile loaded successfully")
    
    # Initialize RuleStore
    rules_path = Path("config/rules.yaml")
    rule_store = RuleStore(str(rules_path))
    
    # Initialize normalizer
    normalizer_config = Path("config/normalizer_rules.yaml")
    normalizer = QuestionNormalizer(
        str(normalizer_config) if normalizer_config.exists() else None
    )
    
    # Initialize LLM Delegate (optional)
    llm_delegate = None
    try:
        # Get LLM settings from config
        llm_settings = LLMSettings()
        llm_client = get_llm_client(llm_settings)
        llm_delegate = OpenAILLMDelegate(llm_client)
        logger.info("LLM delegate initialized")
    except Exception as e:
        logger.warning(f"Could not initialize LLM delegate: {e}. Continuing without LLM fallback.")
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Load the demo form
        demo_form_path = Path(__file__).parent / "index.html"
        if not demo_form_path.exists():
            logger.error(f"Demo form not found: {demo_form_path}")
            await browser.close()
            return
        
        file_url = f"file://{demo_form_path.absolute()}"
        logger.info(f"Loading demo form: {file_url}")
        await page.goto(file_url)
        
        # Wait for page to load
        await page.wait_for_load_state("networkidle")
        
        # Click "Start Test Flow" button
        start_button = page.get_by_role("button", name="Start Test Flow")
        await start_button.click()
        logger.info("Clicked 'Start Test Flow' button")
        
        # Wait for first modal to appear
        await page.wait_for_selector('[role="dialog"]', timeout=5000)
        logger.info("First modal appeared")
        
        # Initialize ModalFlowRunner
        runner = ModalFlowRunner(
            page=page,
            profile=profile,
            rule_store=rule_store,
            normalizer=normalizer,
            llm_delegate=llm_delegate,  # Pass LLM delegate if available
            logger=logger
        )
        
        # Run the flow
        logger.info("Starting modal flow...")
        try:
            await runner.run(max_steps=8)
            logger.info("Modal flow completed successfully!")
        except Exception as e:
            logger.error(f"Error during modal flow: {e}", exc_info=True)
        
        # Wait a bit to see the result
        await asyncio.sleep(2)
        
        # Check if success modal appeared
        success_modal = page.locator('#successModal.active')
        if await success_modal.count() > 0:
            logger.info("✅ Success! Application was submitted.")
        else:
            logger.warning("⚠️ Success modal not found. Flow may not have completed.")
        
        # Keep browser open for inspection (optional)
        await asyncio.sleep(10)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())



