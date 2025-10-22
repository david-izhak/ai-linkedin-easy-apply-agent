from playwright.async_api import Page

from core.selectors import selectors
from .change_text_input import change_text_input


async def insert_phone(page: Page, phone: str) -> None:
    """
    Inserts the phone number into the appropriate field.
    """
    await change_text_input(page, selectors["phone"], phone)
