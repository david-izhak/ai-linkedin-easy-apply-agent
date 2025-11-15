"""
Unit tests for the click_next_button module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apply_form.click_next_button import click_next_button


@pytest.mark.asyncio
class TestClickNextButton:
    """Tests for the click_next_button function."""
    
    async def test_click_next_button(self):
        """Test that click_next_button calls executor methods correctly."""
        # Mock the page, logger, and executor
        mock_page = AsyncMock()
        mock_logger = MagicMock()
        mock_executor = AsyncMock()
        
        # Patch the imports
        with patch("apply_form.click_next_button.get_structured_logger", return_value=mock_logger):
            with patch("apply_form.click_next_button.get_resilience_executor", return_value=mock_executor):
                # Call the function
                await click_next_button(
                    page=mock_page, 
                    job_id="12345", 
                    job_title="Software Engineer"
                )
                
                # Verify executor methods were called with correct arguments
                mock_executor.click.assert_called_once_with(
                    selector_name="next_button",
                    context={"job_id": "12345", "job_title": "Software Engineer"}
                )
                mock_executor.wait_for_selector.assert_called_once()
                
                # Verify logger was used
                assert mock_logger.debug.call_count == 2
                
    async def test_click_next_button_without_context(self):
        """Test that click_next_button works without job_id and job_title."""
        # Mock the page, logger, and executor
        mock_page = AsyncMock()
        mock_logger = MagicMock()
        mock_executor = AsyncMock()
        
        # Patch the imports
        with patch("apply_form.click_next_button.get_structured_logger", return_value=mock_logger):
            with patch("apply_form.click_next_button.get_resilience_executor", return_value=mock_executor):
                # Call the function without job_id and job_title
                await click_next_button(page=mock_page)
                
                # Verify executor methods were called
                mock_executor.click.assert_called_once_with(
                    selector_name="next_button",
                    context={}  # Empty context
                )
                mock_executor.wait_for_selector.assert_called_once()
