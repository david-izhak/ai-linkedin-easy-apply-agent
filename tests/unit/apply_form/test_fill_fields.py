import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from apply_form.fill_fields import fill_fields

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


# Mock the config object that will be passed to the function
@pytest.fixture
def mock_config():
    @dataclass
    class MockFormDataConfig:
        home_city: str = "Test City"
        phone: str = "123456789"
        cv_path: Path = Path("/path/to/cv.pdf")
        text_fields: Dict[str, str] = field(default_factory=lambda: {"salary": "100k"})
        years_of_experience: Dict[str, int] = field(default_factory=lambda: {"python": 5})
        booleans: Dict[str, bool] = field(default_factory=lambda: {"authorized": True})
        requires_visa_sponsorship: bool = False
        language_proficiency: Dict[str, str] = field(default_factory=lambda: {"english": "native"})
        multiple_choice_fields: Dict[str, str] = field(default_factory=lambda: {"pronouns": "they/them"})

    @dataclass
    class MockAppConfig:
        form_data: MockFormDataConfig = field(default_factory=MockFormDataConfig)

    return MockAppConfig()


# This test does NOT use playwright, so it needs the asyncio mark.
@pytest.mark.asyncio
@patch("apply_form.fill_fields.fill_multiple_choice_fields", new_callable=AsyncMock)
@patch("apply_form.fill_fields.fill_boolean", new_callable=AsyncMock)
@patch("apply_form.fill_fields.fill_text_fields", new_callable=AsyncMock)
@patch("apply_form.fill_fields.upload_docs", new_callable=AsyncMock)
@patch("apply_form.fill_fields.uncheck_follow_company", new_callable=AsyncMock)
@patch("apply_form.fill_fields.insert_phone", new_callable=AsyncMock)
@patch("apply_form.fill_fields.insert_home_city", new_callable=AsyncMock)
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
    cover_letter_path = Path("/path/to/cl.pdf")

    await fill_fields(mock_page, mock_config, cover_letter_path)

    # Assert that each function was called once with the mock_page and correct data
    mock_insert_home_city.assert_called_once_with(mock_page, "Test City")
    mock_insert_phone.assert_called_once_with(mock_page, "123456789")
    mock_uncheck_follow_company.assert_called_once_with(mock_page)
    mock_upload_docs.assert_called_once_with(
        mock_page, Path("/path/to/cv.pdf"), cover_letter_path
    )

    # Assert that text fields are combined and passed correctly
    expected_text_fields = {"salary": "100k", "python": 5}
    mock_fill_text_fields.assert_called_once_with(mock_page, expected_text_fields)

    # Assert that booleans are combined and passed correctly
    expected_booleans = {"authorized": True, "sponsorship": False}
    mock_fill_boolean.assert_called_once_with(mock_page, expected_booleans)

    # Assert that multiple choice fields are combined and passed correctly
    expected_mc_fields = {"english": "native", "pronouns": "they/them"}
    mock_fill_multiple_choice_fields.assert_called_once_with(
        mock_page, expected_mc_fields
    )
