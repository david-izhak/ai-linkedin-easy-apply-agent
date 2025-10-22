import pytest
from playwright.sync_api import Page, sync_playwright


@pytest.fixture(scope="session")
def browser():
    """Create a browser instance for integration tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) # Use headless mode for tests
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """Create a new page for each test."""
    context = browser.new_context()
    page = context.new_page()
    yield page
    context.close()