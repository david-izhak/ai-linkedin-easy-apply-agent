import pytest
from unittest.mock import AsyncMock
import sys
import os
from apply_form.wait_for_no_error import wait_for_no_error

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestWaitForNoError:

    @pytest.mark.asyncio
    async def test_wait_for_no_error_no_errors(self):
        """Test waiting when no error elements are present."""
        mock_page = AsyncMock()

        await wait_for_no_error(mock_page)

        mock_page.wait_for_function.assert_called_once_with(
            '() => !document.querySelector(\'div[id*="error"] div[class*="error"]\')',
            timeout=1000,
        )
