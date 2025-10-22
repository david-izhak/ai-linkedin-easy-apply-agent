import pytest
from unittest.mock import AsyncMock, patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from apply_form.insert_home_city import insert_home_city


class TestInsertHomeCity:
    
    @pytest.mark.asyncio
    @patch('apply_form.insert_home_city.change_text_input')
    async def test_insert_home_city_success(self, mock_change_text_input):
        """Test successful insertion of home city."""
        mock_page = AsyncMock()
        home_city = "New York, NY"
        
        await insert_home_city(mock_page, home_city)
        
        mock_change_text_input.assert_called_once_with(mock_page, ".jobs-easy-apply-modal input[id*='easyApplyFormElement'][id*='city-HOME-CITY']", home_city)