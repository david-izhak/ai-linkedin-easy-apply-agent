import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os
from apply_form.change_text_input import change_text_input
from playwright.async_api import ElementHandle

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestChangeTextInput:

    @pytest.mark.asyncio
    async def test_change_text_input_with_selector(self):
        """Test changing text input with a selector provided."""
        mock_container = AsyncMock()
        mock_element = AsyncMock()
        mock_container.query_selector.return_value = mock_element
        mock_element.input_value.return_value = "old_value"

        await change_text_input(mock_container, "input#test", "new_value")

        mock_container.query_selector.assert_called_once_with("input#test")
        mock_element.click.assert_called_once_with(click_count=3)
        mock_element.type.assert_called_once_with("new_value")

    @pytest.mark.asyncio
    async def test_change_text_input_without_selector(self):
        """Test changing text input when container is the element itself."""
        # Create a proper ElementHandle mock
        mock_element = MagicMock(spec=ElementHandle)
        mock_element.input_value = AsyncMock(return_value="old_value")
        mock_element.click = AsyncMock()
        mock_element.type = AsyncMock()

        await change_text_input(mock_element, "", "new_value")

        mock_element.click.assert_called_once_with(click_count=3)
        mock_element.type.assert_called_once_with("new_value")

    @pytest.mark.asyncio
    async def test_change_text_input_value_different(self):
        """Test that text is only changed if it's different."""
        mock_container = AsyncMock()
        mock_element = AsyncMock()
        mock_container.query_selector.return_value = mock_element
        mock_element.input_value.return_value = "same_value"

        await change_text_input(mock_container, "input#test", "same_value")

        mock_container.query_selector.assert_called_once_with("input#test")
        # Should not click or type since values are the same
        mock_element.click.assert_not_called()
        mock_element.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_change_text_input_element_not_found(self):
        """Test handling when element is not found with selector."""
        mock_container = AsyncMock()
        mock_container.query_selector.return_value = None

        with pytest.raises(
            ValueError, match="Could not find element with selector input#test"
        ):
            await change_text_input(mock_container, "input#test", "new_value")

    @pytest.mark.asyncio
    async def test_change_text_input_container_type_error(self):
        """Test handling when container is not ElementHandle without selector."""
        mock_page = AsyncMock()  # This is not an ElementHandle

        with pytest.raises(
            TypeError,
            match="If no selector is provided, the container must be an ElementHandle, not a Page.",
        ):
            await change_text_input(mock_page, "", "new_value")
