import pytest_asyncio
from playwright.async_api import async_playwright


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def browser():
    """Create a browser instance for integration tests."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)  # Use headless mode for tests
        yield browser
        await browser.close()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def page(browser):
    """Create a new page for each test."""
    context = await browser.new_context()
    page = await context.new_page()
    yield page
    await context.close()
