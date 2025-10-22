import pytest
from unittest.mock import AsyncMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))
from core.selectors import selectors

from apply_form.click_next_button import click_next_button


class TestClickNextButton:
    
    @pytest.mark.asyncio
    async def test_click_next_button_success(self):
        """Test successful click of the next button."""
        mock_page = AsyncMock()
        
        await click_next_button(mock_page)
        
        mock_page.click.assert_called_once_with(selectors["next_button"])
        mock_page.wait_for_selector.assert_called_once_with(
            selectors["enabled_submit_or_next_button"], timeout=1000
        )