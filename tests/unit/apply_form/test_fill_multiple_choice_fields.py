import pytest
from unittest.mock import AsyncMock, patch
import sys
import os
from core.selectors import selectors

from apply_form.fill_multiple_choice_fields import (
    fill_multiple_choice_fields,
    _process_select_element,
)

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestProcessSelectElement:

    @pytest.mark.asyncio
    async def test_process_select_element_match_and_select(self):
        """Test processing a select element that matches a pattern and selects the correct option."""
        mock_page = AsyncMock()
        mock_select = AsyncMock()
        mock_option1 = AsyncMock()
        mock_option2 = AsyncMock()

        mock_select.query_selector_all.return_value = [mock_option1, mock_option2]
        mock_option1.inner_text.return_value = "Beginner"
        mock_option2.inner_text.return_value = "Professional"

        mock_select.get_attribute.return_value = "select_id"

        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "English Proficiency"

        mock_option2.get_attribute.return_value = "prof_value"

        multiple_choice_fields = {"english": "professional"}

        await _process_select_element(mock_page, mock_select, multiple_choice_fields)

        mock_select.query_selector_all.assert_called_once_with(selectors["option"])
        mock_select.get_attribute.assert_called_once_with("id")
        mock_page.query_selector.assert_called_once_with("label[for='select_id']")
        mock_select.select_option.assert_called_once_with(value="prof_value")

    @pytest.mark.asyncio
    async def test_process_select_element_no_matching_label(self):
        """Test processing a select element with no matching label."""
        mock_page = AsyncMock()
        mock_select = AsyncMock()
        # No need to mock options if query_selector_all is not called

        mock_select.get_attribute.return_value = "select_id"

        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "Some Other Field"

        multiple_choice_fields = {"english": "professional"}

        await _process_select_element(mock_page, mock_select, multiple_choice_fields)

        mock_select.query_selector_all.assert_not_called()
        mock_select.get_attribute.assert_called_once_with("id")
        mock_page.query_selector.assert_called_once_with("label[for='select_id']")
        # Should not select anything since no matching label
        mock_select.select_option.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_select_element_no_matching_option(self):
        """Test processing a select element where no option matches the desired value."""
        mock_page = AsyncMock()
        mock_select = AsyncMock()
        mock_option1 = AsyncMock()
        mock_option2 = AsyncMock()

        mock_select.query_selector_all.return_value = [mock_option1, mock_option2]
        mock_option1.inner_text.return_value = "Beginner"
        mock_option2.inner_text.return_value = "Professional"

        mock_select.get_attribute.return_value = "select_id"

        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "English Proficiency"

        multiple_choice_fields = {"english": "native"}  # No matching option

        await _process_select_element(mock_page, mock_select, multiple_choice_fields)

        mock_select.query_selector_all.assert_called_once_with(selectors["option"])
        mock_select.get_attribute.assert_called_once_with("id")
        mock_page.query_selector.assert_called_once_with("label[for='select_id']")
        # Should not select anything since no matching option
        mock_select.select_option.assert_not_called()


class TestFillMultipleChoiceFields:

    @pytest.mark.asyncio
    @patch("apply_form.fill_multiple_choice_fields._process_select_element")
    async def test_fill_multiple_choice_fields_multiple_selects(
        self, mock_process_select
    ):
        """Test filling multiple choice fields across multiple select elements."""
        mock_page = AsyncMock()
        mock_select1 = AsyncMock()
        mock_select2 = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_select1, mock_select2]

        multiple_choice_fields = {"english": "professional", "pronouns": "he/him"}

        await fill_multiple_choice_fields(mock_page, multiple_choice_fields)

        mock_page.query_selector_all.assert_called_once_with(selectors["select"])
        assert mock_process_select.call_count == 2
        mock_process_select.assert_any_call(
            mock_page, mock_select1, multiple_choice_fields
        )
        mock_process_select.assert_any_call(
            mock_page, mock_select2, multiple_choice_fields
        )
