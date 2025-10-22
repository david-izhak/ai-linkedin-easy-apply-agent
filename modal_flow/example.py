"""
Example usage of ModalFlowRunner.

This demonstrates how to use the modal flow engine to fill LinkedIn Easy Apply forms.
"""

import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from modal_flow.modal_flow import ModalFlowRunner
from modal_flow.profile_store import ProfileStore
from modal_flow.rules_store import RuleStore
from modal_flow.normalizer import QuestionNormalizer


async def main():
    """Example main function."""
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Load profile
    profile_store = ProfileStore("config/profile_example.json")
    profile = profile_store.load()
    
    # Load rules
    rule_store = RuleStore("config/rules.yaml")
    
    # Initialize normalizer
    normalizer = QuestionNormalizer("config/normalizer_rules.yaml")
    
    # Note: LLM delegate would be initialized here if needed
    # llm_delegate = OpenAILLMDelegate(api_key="...")
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Navigate to LinkedIn job page and click Easy Apply
        # (This part is assumed to be handled by existing code)
        # await page.goto("https://www.linkedin.com/jobs/view/...")
        # await page.click("button:has-text('Easy Apply')")
        
        # Initialize ModalFlowRunner
        runner = ModalFlowRunner(
            page=page,
            profile=profile,
            rule_store=rule_store,
            normalizer=normalizer,
            llm_delegate=None,  # Add if needed
        )
        
        # Run the flow
        result = await runner.run(max_steps=8)
        logging.info(
            "Modal flow finished completed=%s submitted=%s validation_errors=%s",
            result.completed,
            result.submitted,
            result.validation_errors,
        )
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

