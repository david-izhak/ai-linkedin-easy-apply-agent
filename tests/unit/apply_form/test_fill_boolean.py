import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from apply_form.fill_boolean import fill_boolean, _process_single_radio_fieldset, _fill_radio_buttons, _process_single_checkbox, _fill_checkboxes, _process_single_select, _fill_two_option_selects
from core.selectors import selectors


class TestProcessSingleRadioFieldset:
    
    @pytest.mark.asyncio
    async def test_process_single_radio_fieldset_two_options_match(self):
        """Test processing a radio fieldset with two options that match the pattern."""
        mock_fieldset = AsyncMock()
        mock_radio1 = AsyncMock()
        mock_radio2 = AsyncMock()
        mock_fieldset.query_selector_all.return_value = [mock_radio1, mock_radio2]
        
        mock_legend = AsyncMock()
        mock_legend.inner_text.return_value = "Do you require sponsorship?"
        
        async def query_selector_side_effect(selector):
            if selector == "legend":
                return mock_legend
            elif selector == f"{selectors['radio_input']}[value='Yes']":
                return mock_radio1
            return None

        mock_fieldset.query_selector.side_effect = query_selector_side_effect
        
        mock_radio1.get_attribute.return_value = "Yes"
        mock_radio2.get_attribute.return_value = "No"
        
        booleans = {"sponsorship": True}
        
        await _process_single_radio_fieldset(mock_fieldset, booleans)
        
        mock_fieldset.query_selector_all.assert_called_once()
        assert mock_fieldset.query_selector.call_count == 2
        mock_fieldset.query_selector.assert_any_call("legend")
        mock_fieldset.query_selector.assert_any_call(f"{selectors['radio_input']}[value='Yes']")
        mock_radio1.click.assert_called_once()
        mock_radio2.click.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_single_radio_fieldset_not_two_options(self):
        """Test processing a radio fieldset that doesn't have exactly two options."""
        mock_fieldset = AsyncMock()
        mock_radio1 = AsyncMock()
        mock_radio2 = AsyncMock()
        mock_radio3 = AsyncMock()
        mock_fieldset.query_selector_all.return_value = [mock_radio1, mock_radio2, mock_radio3]
        
        booleans = {"sponsorship": True}
        
        await _process_single_radio_fieldset(mock_fieldset, booleans)
        
        mock_fieldset.query_selector_all.assert_called_once()
        # Should return early since not exactly 2 options
        mock_fieldset.query_selector.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_process_single_radio_fieldset_no_legend(self):
        """Test processing a radio fieldset with no legend."""
        mock_fieldset = AsyncMock()
        mock_radio1 = AsyncMock()
        mock_radio2 = AsyncMock()
        mock_fieldset.query_selector_all.return_value = [mock_radio1, mock_radio2]
        
        mock_fieldset.query_selector.return_value = None  # No legend
        
        booleans = {"sponsorship": True}
        
        await _process_single_radio_fieldset(mock_fieldset, booleans)
        
        mock_fieldset.query_selector_all.assert_called_once()
        mock_fieldset.query_selector.assert_called_once_with("legend")
        # Should return early since no legend
        mock_radio1.get_attribute.assert_not_called()


class TestFillRadioButtons:
    
    @pytest.mark.asyncio
    @patch('apply_form.fill_boolean._process_single_radio_fieldset', new_callable=AsyncMock)
    async def test_fill_radio_buttons_multiple_fieldsets(self, mock_process_single_radio_fieldset):
        """Test filling radio buttons across multiple fieldsets."""
        mock_page = AsyncMock()
        mock_fieldset1 = AsyncMock()
        mock_fieldset2 = AsyncMock()
        mock_page.query_selector_all.return_value = [mock_fieldset1, mock_fieldset2]
        
        booleans = {"sponsorship": True}
        await _fill_radio_buttons(mock_page, booleans)
        
        mock_page.query_selector_all.assert_called_once_with(selectors["fieldset"])
        assert mock_process_single_radio_fieldset.call_count == 2
        mock_process_single_radio_fieldset.assert_any_call(mock_fieldset1, booleans)
        mock_process_single_radio_fieldset.assert_any_call(mock_fieldset2, booleans)


class TestProcessSingleCheckbox:
    
    @pytest.mark.asyncio
    async def test_process_single_checkbox_match_and_not_checked(self):
        """Test processing a checkbox that matches and is not checked."""
        mock_page = AsyncMock()
        mock_checkbox = AsyncMock()
        mock_checkbox.get_attribute.return_value = "checkbox_id"
        
        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "Authorized to work in the US"
        
        mock_checkbox.is_checked.return_value = False  # Not checked
        booleans = {"authorized": True}
        
        await _process_single_checkbox(mock_page, mock_checkbox, booleans)
        
        mock_checkbox.get_attribute.assert_called_once_with("id")
        mock_page.query_selector.assert_called_once_with("label[for='checkbox_id']")
        mock_checkbox.is_checked.assert_called_once()
        mock_checkbox.click.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_single_checkbox_match_and_checked_correctly(self):
        """Test processing a checkbox that matches and is already checked correctly."""
        mock_page = AsyncMock()
        mock_checkbox = AsyncMock()
        mock_checkbox.get_attribute.return_value = "checkbox_id"
        
        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "Authorized to work in the US"
        
        mock_checkbox.is_checked.return_value = True  # Checked
        booleans = {"authorized": True}
        
        await _process_single_checkbox(mock_page, mock_checkbox, booleans)
        
        mock_checkbox.get_attribute.assert_called_once_with("id")
        mock_page.query_selector.assert_called_once_with("label[for='checkbox_id']")
        mock_checkbox.is_checked.assert_called_once()
        # Should not click since already correct
        mock_checkbox.click.assert_not_called()


class TestProcessSingleSelect:
    
    @pytest.mark.asyncio
    async def test_process_single_select_two_options_match(self):
        """Test processing a select with two options that match the pattern."""
        mock_page = AsyncMock()
        mock_select = AsyncMock()
        mock_option1 = AsyncMock()
        mock_option2 = AsyncMock()
        
        # Directly provide the options list without the placeholder for this test
        mock_select.query_selector_all.return_value = [mock_option1, mock_option2]
        mock_option1.inner_text.return_value = "No"
        mock_option2.inner_text.return_value = "Yes"
        
        mock_select.get_attribute.return_value = "select_id"
        
        mock_label = AsyncMock()
        mock_page.query_selector.return_value = mock_label
        mock_label.inner_text.return_value = "Do you have a degree?"
        
        mock_option1.get_attribute.return_value = "no_value"
        mock_option2.get_attribute.return_value = "yes_value"
        
        booleans = {"degree": True}
        
        await _process_single_select(mock_page, mock_select, booleans)
        
        mock_select.query_selector_all.assert_called_once()
        mock_select.get_attribute.assert_called_once_with("id")
        mock_page.query_selector.assert_called_once_with("label[for='select_id']")
        mock_select.select_option.assert_called_once_with(value="yes_value")


class TestFillBoolean:
    
    @pytest.mark.asyncio
    @patch('apply_form.fill_boolean._fill_radio_buttons')
    @patch('apply_form.fill_boolean._fill_checkboxes')
    @patch('apply_form.fill_boolean._fill_two_option_selects')
    async def test_fill_boolean_orchestrates_all_types(self, mock_fill_selects, mock_fill_checkboxes, mock_fill_radios):
        """Test that fill_boolean orchestrates all types of boolean fields."""
        mock_page = AsyncMock()
        booleans = {"test": True}
        
        await fill_boolean(mock_page, booleans)
        
        mock_fill_radios.assert_called_once_with(mock_page, booleans)
        mock_fill_checkboxes.assert_called_once_with(mock_page, booleans)
        mock_fill_selects.assert_called_once_with(mock_page, booleans)