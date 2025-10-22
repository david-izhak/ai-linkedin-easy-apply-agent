import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from actions.apply import click_easy_apply_button, apply_to_job


class TestClickEasyApplyButton:
    
    @pytest.mark.asyncio
    async def test_click_easy_apply_button_success(self):
        """Test that the easy apply button is clicked successfully."""
        mock_page = AsyncMock()
        mock_selector = AsyncMock()
        mock_page.wait_for_selector.return_value = mock_selector
        
        await click_easy_apply_button(mock_page)
        
        mock_page.wait_for_selector.assert_called_once_with(
            "button.jobs-apply-button:enabled", timeout=10000
        )
        mock_page.click.assert_called_once_with("button.jobs-apply-button:enabled")
    
    @pytest.mark.asyncio
    async def test_click_easy_apply_button_timeout(self):
        """Test handling of timeout when waiting for the easy apply button."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = TimeoutError()
        
        with pytest.raises(TimeoutError):
            await click_easy_apply_button(mock_page)


class TestApplyToJob:
    
    @pytest.mark.asyncio
    @patch('actions.apply.click_easy_apply_button')
    @patch('actions.apply.fill_fields')
    @patch('actions.apply.click_next_button')
    @patch('actions.apply.wait_for_no_error')
    async def test_apply_to_job_success_with_submit(self, mock_wait_for_no_error, 
                                                   mock_click_next_button, 
                                                   mock_fill_fields, 
                                                   mock_click_easy_apply_button):
        """Test successful application with submission."""
        mock_page = AsyncMock()
        mock_submit_button = AsyncMock()
        mock_page.query_selector.side_effect = [mock_submit_button, mock_submit_button]  # First call for loop check, second for final check
        
        mock_config = MagicMock()
        should_submit = True
        
        await apply_to_job(mock_page, "job_link", mock_config, should_submit)
        
        mock_click_easy_apply_button.assert_called_once_with(mock_page)
        assert mock_fill_fields.call_count == 1  # Called once in the loop
        assert mock_click_next_button.call_count == 1  # Called once in the loop
        assert mock_wait_for_no_error.call_count == 1  # Called once in the loop
        mock_submit_button.click.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('actions.apply.click_easy_apply_button')
    @patch('actions.apply.fill_fields')
    @patch('actions.apply.click_next_button')
    @patch('actions.apply.wait_for_no_error')
    async def test_apply_to_job_success_without_submit(self, mock_wait_for_no_error,
                                                      mock_click_next_button, 
                                                      mock_fill_fields, 
                                                      mock_click_easy_apply_button):
        """Test successful application without submission (dry run)."""
        mock_page = AsyncMock()
        mock_submit_button = AsyncMock()
        mock_page.query_selector.side_effect = [mock_submit_button, mock_submit_button]  # First call for loop check, second for final check
        
        mock_config = MagicMock()
        should_submit = False
        
        await apply_to_job(mock_page, "job_link", mock_config, should_submit)
        
        mock_click_easy_apply_button.assert_called_once_with(mock_page)
        assert mock_fill_fields.call_count == 1  # Called once in the loop
        assert mock_click_next_button.call_count == 1  # Called once in the loop
        assert mock_wait_for_no_error.call_count == 1  # Called once in the loop
        mock_submit_button.click.assert_not_called()  # Should not be called in dry run
    
    @pytest.mark.asyncio
    @patch('actions.apply.click_easy_apply_button')
    async def test_apply_to_job_easy_apply_button_error(self, mock_click_easy_apply_button):
        """Test handling of error when clicking easy apply button."""
        mock_page = AsyncMock()
        mock_click_easy_apply_button.side_effect = Exception("Button not found")
        
        mock_config = MagicMock()
        should_submit = True
        
        with pytest.raises(Exception, match="Button not found"):
            await apply_to_job(mock_page, "job_link", mock_config, should_submit)
    
    @pytest.mark.asyncio
    @patch('actions.apply.click_easy_apply_button')
    @patch('actions.apply.fill_fields')
    @patch('actions.apply.click_next_button')
    @patch('actions.apply.wait_for_no_error')
    async def test_apply_to_job_submit_button_not_found(self, mock_wait_for_no_error, 
                                                       mock_click_next_button, 
                                                       mock_fill_fields, 
                                                       mock_click_easy_apply_button):
        """Test handling of case when submit button is not found after max pages."""
        mock_page = AsyncMock()
        mock_page.query_selector.return_value = None  # No submit button found
        
        mock_config = MagicMock()
        should_submit = True
        
        with pytest.raises(RuntimeError, match="Submit button not found after 5 pages"):
            await apply_to_job(mock_page, "job_link", mock_config, should_submit)
        
        # Should have called fill_fields, click_next_button, and wait_for_no_error max_pages times
        assert mock_fill_fields.call_count == 5
        assert mock_click_next_button.call_count == 5
        assert mock_wait_for_no_error.call_count == 5
    
    @pytest.mark.asyncio
    @patch('actions.apply.click_easy_apply_button')
    @patch('actions.apply.fill_fields')
    @patch('actions.apply.click_next_button')
    @patch('actions.apply.wait_for_no_error')
    async def test_apply_to_job_multiple_pages(self, mock_wait_for_no_error, 
                                              mock_click_next_button, 
                                              mock_fill_fields, 
                                              mock_click_easy_apply_button):
        """Test handling of multi-page application form."""
        mock_page = AsyncMock()
        # Return submit button only on the 3rd iteration
        submit_buttons = [None, None, AsyncMock(), AsyncMock(), AsyncMock()]
        mock_page.query_selector.side_effect = submit_buttons
        
        mock_config = MagicMock()
        should_submit = False
        
        await apply_to_job(mock_page, "job_link", mock_config, should_submit)
        
        # Should have called fill_fields, click_next_button, and wait_for_no_error 3 times
        assert mock_fill_fields.call_count == 3
        assert mock_click_next_button.call_count == 3
        assert mock_wait_for_no_error.call_count == 3