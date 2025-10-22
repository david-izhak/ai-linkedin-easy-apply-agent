import pytest
from unittest.mock import AsyncMock, patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from apply_form.insert_phone import insert_phone


class TestInsertPhone:
    
    @pytest.mark.asyncio
    @patch('apply_form.insert_phone.change_text_input')
    async def test_insert_phone_success(self, mock_change_text_input):
        """Test successful insertion of phone number."""
        mock_page = AsyncMock()
        phone = "123-456-7890"
        
        await insert_phone(mock_page, phone)
        
        mock_change_text_input.assert_called_once_with(mock_page, ".jobs-easy-apply-modal input[id*='easyApplyFormElement'][id*='phoneNumber']", phone)