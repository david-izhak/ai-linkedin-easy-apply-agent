import pytest
from unittest.mock import AsyncMock, patch
import sys
import os
from core.selectors import selectors
from apply_form.fill_text_fields import fill_text_fields

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestFillTextFields:

    @pytest.mark.asyncio
    @patch("apply_form.fill_text_fields.change_text_input")
    async def test_fill_text_fields_match_and_fill(self, mock_change_text_input):
        """Test filling text fields that match a pattern."""
        mock_page = AsyncMock()
        mock_input1 = AsyncMock()
        mock_input2 = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_input1, mock_input2]

        mock_input1.get_attribute.return_value = "input1_id"
        mock_input2.get_attribute.return_value = "input2_id"

        mock_label1 = AsyncMock()
        mock_label2 = AsyncMock()
        mock_page.query_selector.side_effect = [mock_label1, mock_label2]
        mock_label1.inner_text.return_value = "Years of Experience"
        mock_label2.inner_text.return_value = "Phone Number"

        text_fields = {"experience": "5", "phone": "123-456-7890"}

        await fill_text_fields(mock_page, text_fields)

        mock_page.query_selector_all.assert_called_once_with(selectors["text_input"])
        assert mock_page.query_selector.call_count == 2
        # Should call change_text_input for both matching fields
        assert mock_change_text_input.call_count == 2
        mock_change_text_input.assert_any_call(mock_input1, "", "5")
        mock_change_text_input.assert_any_call(mock_input2, "", "123-456-7890")

    @pytest.mark.asyncio
    @patch("apply_form.fill_text_fields.change_text_input")
    async def test_fill_text_fields_no_matching_label(self, mock_change_text_input):
        """Test filling text fields when no label matches."""
        mock_page = AsyncMock()
        mock_input = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_input]

        mock_input.get_attribute.return_value = "input_id"

        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "Some Other Field"

        text_fields = {"experience": "5", "phone": "123-456-7890"}

        await fill_text_fields(mock_page, text_fields)

        mock_page.query_selector_all.assert_called_once_with(selectors["text_input"])
        mock_page.query_selector.assert_called_once_with("label[for='input_id']")
        # Should not call change_text_input since no matching label
        mock_change_text_input.assert_not_called()

    @pytest.mark.asyncio
    @patch("apply_form.fill_text_fields.change_text_input")
    async def test_fill_text_fields_label_lookup_fails(self, mock_change_text_input):
        """Test handling when label lookup fails."""
        mock_page = AsyncMock()
        mock_input = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_input]

        mock_input.get_attribute.return_value = "input_id"

        mock_page.query_selector.side_effect = Exception("Lookup failed")

        text_fields = {"experience": "5", "phone": "123-456-7890"}

        await fill_text_fields(mock_page, text_fields)

        mock_page.query_selector_all.assert_called_once_with(selectors["text_input"])
        mock_page.query_selector.assert_called_once_with("label[for='input_id']")
        # Should continue to next input after logging the error
        mock_change_text_input.assert_not_called()
