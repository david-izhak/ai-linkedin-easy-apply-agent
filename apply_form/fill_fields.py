from playwright.async_api import Page
from typing import Optional
from pathlib import Path

from config import AppConfig # Import AppConfig
from .fill_multiple_choice_fields import fill_multiple_choice_fields
from .fill_boolean import fill_boolean
from .fill_text_fields import fill_text_fields
from .insert_home_city import insert_home_city
from .insert_phone import insert_phone
from .uncheck_follow_company import uncheck_follow_company
from .upload_docs import upload_docs


async def fill_fields(
    page: Page,
    app_config: AppConfig,
    cover_letter_path: Optional[Path] = None
) -> None:
    """
    Orchestrates filling with all types of fields in the application form.
    """
    await insert_home_city(page, app_config.form_data.home_city)
    await insert_phone(page, app_config.form_data.phone)
    await uncheck_follow_company(page)

    await upload_docs(page, app_config.form_data.cv_path, cover_letter_path)

    # Combine text fields and years of experience into one dictionary
    text_fields = {**app_config.form_data.text_fields, **app_config.form_data.years_of_experience}
    await fill_text_fields(page, text_fields)

    # Add the visa sponsorship requirement to the booleans dict
    booleans = app_config.form_data.booleans.copy()
    booleans["sponsorship"] = app_config.form_data.requires_visa_sponsorship
    await fill_boolean(page, booleans)

    # Combine language proficiency and other multiple choice fields
    multiple_choice_fields = {
        **app_config.form_data.language_proficiency,
        **app_config.form_data.multiple_choice_fields,
    }
    await fill_multiple_choice_fields(page, multiple_choice_fields)
