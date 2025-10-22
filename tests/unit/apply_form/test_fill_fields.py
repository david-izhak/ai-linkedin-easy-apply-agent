import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Adjust the python path to import the module
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from apply_form.fill_fields import fill_fields

# Mock the config object that will be passed to the function
@pytest.fixture
def mock_config():
    config = MagicMock()
    config.HOME_CITY = "Test City"
    config.PHONE = "123456789"
    config.CV_PATH = "/path/to/cv.pdf"
    config.COVER_LETTER_PATH = "/path/to/cl.pdf"
    config.TEXT_FIELDS = {"salary": "100k"}
    config.YEARS_OF_EXPERIENCE = {"python": 5}
    config.BOOLEANS = {"authorized": True}
    config.REQUIRES_VISA_SPONSORSHIP = False
    config.LANGUAGE_PROFICIENCY = {"english": "native"}
    config.MULTIPLE_CHOICE_FIELDS = {"pronouns": "they/them"}
    return config

# This test does NOT use playwright, so it needs the asyncio mark.
@pytest.mark.asyncio
@patch('apply_form.fill_fields.fill_multiple_choice_fields', new_callable=AsyncMock)
@patch('apply_form.fill_fields.fill_boolean', new_callable=AsyncMock)
@patch('apply_form.fill_fields.fill_text_fields', new_callable=AsyncMock)
@patch('apply_form.fill_fields.upload_docs', new_callable=AsyncMock)
@patch('apply_form.fill_fields.uncheck_follow_company', new_callable=AsyncMock)
@patch('apply_form.fill_fields.insert_phone', new_callable=AsyncMock)
@patch('apply_form.fill_fields.insert_home_city', new_callable=AsyncMock)
async def test_fill_fields_orchestration(
    mock_insert_home_city,
    mock_insert_phone,
    mock_uncheck_follow_company,
    mock_upload_docs,
    mock_fill_text_fields,
    mock_fill_boolean,
    mock_fill_multiple_choice_fields,
    mock_config,
):
    """Test that fill_fields calls all helper functions with the correct arguments."""
    # This test doesn't use a real page, so a simple AsyncMock is sufficient.
    mock_page = AsyncMock()

    await fill_fields(mock_page, mock_config)

    # Assert that each function was called once with the mock_page and correct data
    mock_insert_home_city.assert_called_once_with(mock_page, "Test City")
    mock_insert_phone.assert_called_once_with(mock_page, "123456789")
    mock_uncheck_follow_company.assert_called_once_with(mock_page)
    mock_upload_docs.assert_called_once_with(mock_page, "/path/to/cv.pdf", "/path/to/cl.pdf")

    # Assert that text fields are combined and passed correctly
    expected_text_fields = {"salary": "100k", "python": 5}
    mock_fill_text_fields.assert_called_once_with(mock_page, expected_text_fields)

    # Assert that booleans are combined and passed correctly
    expected_booleans = {"authorized": True, "sponsorship": False}
    mock_fill_boolean.assert_called_once_with(mock_page, expected_booleans)

    # Assert that multiple choice fields are combined and passed correctly
    expected_mc_fields = {"english": "native", "pronouns": "they/them"}
    mock_fill_multiple_choice_fields.assert_called_once_with(mock_page, expected_mc_fields)
