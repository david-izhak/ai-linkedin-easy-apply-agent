from playwright.async_api import Page

from core.selectors import selectors
from .change_text_input import change_text_input


async def insert_home_city(page: Page, home_city: str) -> None:
    """
    Inserts the home city into the appropriate field.
    """
    await change_text_input(page, selectors["home_city"], home_city)
