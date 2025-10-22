from playwright.async_api import Page
from .fill_multiple_choice_fields import fill_multiple_choice_fields
from .fill_boolean import fill_boolean
from .fill_text_fields import fill_text_fields
from .insert_home_city import insert_home_city
from .insert_phone import insert_phone
from .uncheck_follow_company import uncheck_follow_company
from .upload_docs import upload_docs


async def fill_fields(page: Page, config) -> None:
    """
    Orchestrates filling with all types of fields in the application form.
    """
    await insert_home_city(page, config.HOME_CITY)
    await insert_phone(page, config.PHONE)
    await uncheck_follow_company(page)

    await upload_docs(page, config.CV_PATH, config.COVER_LETTER_PATH)

    # Combine text fields and years of experience into one dictionary
    text_fields = {**config.TEXT_FIELDS, **config.YEARS_OF_EXPERIENCE}
    await fill_text_fields(page, text_fields)

    # Add the visa sponsorship requirement to the booleans dict
    booleans = config.BOOLEANS.copy()
    booleans["sponsorship"] = config.REQUIRES_VISA_SPONSORSHIP
    await fill_boolean(page, booleans)

    # Combine language proficiency and other multiple choice fields
    multiple_choice_fields = {
        **config.LANGUAGE_PROFICIENCY,
        **config.MULTIPLE_CHOICE_FIELDS,
    }
    await fill_multiple_choice_fields(page, multiple_choice_fields)
