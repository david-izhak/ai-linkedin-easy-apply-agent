import pytest
from unittest.mock import AsyncMock
import sys
import os
from apply_form.uncheck_follow_company import uncheck_follow_company

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestUncheckFollowCompany:

    @pytest.mark.asyncio
    async def test_uncheck_follow_company_when_checked(self):
        """Test unchecking the follow company checkbox when it's checked."""
        mock_page = AsyncMock()
        mock_checkbox = AsyncMock()
        mock_page.query_selector.return_value = mock_checkbox
        mock_page.evaluate.return_value = True  # Checkbox is checked

        await uncheck_follow_company(mock_page)

        mock_page.query_selector.assert_called_once_with(
            '.jobs-easy-apply-modal input[type="checkbox"][id*="follow-company-checkbox"]'
        )
        mock_page.evaluate.assert_called_once_with("el => el.checked", mock_checkbox)
        mock_checkbox.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_uncheck_follow_company_when_not_checked(self):
        """Test that nothing happens when the follow company checkbox is not checked."""
        mock_page = AsyncMock()
        mock_checkbox = AsyncMock()
        mock_page.query_selector.return_value = mock_checkbox
        mock_page.evaluate.return_value = False  # Checkbox is not checked

        await uncheck_follow_company(mock_page)

        mock_page.query_selector.assert_called_once_with(
            '.jobs-easy-apply-modal input[type="checkbox"][id*="follow-company-checkbox"]'
        )
        mock_page.evaluate.assert_called_once_with("el => el.checked", mock_checkbox)
        # Should not click since it's not checked
        mock_checkbox.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_uncheck_follow_company_checkbox_not_found(self):
        """Test handling when the follow company checkbox is not found."""
        mock_page = AsyncMock()
        mock_page.query_selector.return_value = None  # Checkbox not found

        await uncheck_follow_company(mock_page)

        mock_page.query_selector.assert_called_once_with(
            '.jobs-easy-apply-modal input[type="checkbox"][id*="follow-company-checkbox"]'
        )
        # Should not evaluate or click since checkbox is None
        mock_page.evaluate.assert_not_called()
