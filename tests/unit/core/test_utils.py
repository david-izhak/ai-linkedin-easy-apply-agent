from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os
import pytest
from core.utils import (
    ask_user,
    # wait,
    wait_for_any_selector,
    # check_any_selector_present
)

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestAskUser:
    """Test suite for ask_user function."""

    @patch("builtins.input", return_value="user_input")
    @patch("builtins.print")
    def test_ask_user_returns_input(self, mock_print, mock_input):
        """Test that ask_user prints the prompt and returns user input."""
        prompt = "Enter your name: "
        result = ask_user(prompt)

        mock_print.assert_called_once_with(prompt, end="")
        mock_input.assert_called_once()
        assert result == "user_input"


# class TestWait:
#     """Test suite for wait function."""
#
#     @patch("core.utils.time")
#     def test_wait_correct_duration(self, mock_time):
#         """Test that wait function sleeps for the correct duration in seconds."""
#         time_ms = 2000  # 2 seconds
#
#         wait(time_ms)
#
#         mock_time.sleep.assert_called_once_with(2.0)  # 2000 ms = 2.0 seconds
#
#     @patch("core.utils.time")
#     def test_wait_converts_ms_to_seconds(self, mock_time):
#         """Test that wait function correctly converts milliseconds to seconds."""
#         time_ms = 500  # 0.5 seconds
#
#         wait(time_ms)
#
#         mock_time.sleep.assert_called_once_with(0.5)  # 500 ms = 0.5 seconds


class TestWaitForAnySelector:
    """Test suite for wait_for_any_selector function."""

    @pytest.mark.asyncio
    async def test_returns_first_found_selector(self):
        """Test that function returns one of the selectors when found."""
        mock_page = AsyncMock()
        mock_element = MagicMock()
        
        # All selectors succeed (parallel execution, any can be first)
        mock_page.wait_for_selector.return_value = mock_element
        
        selectors = ["div.first", "div.second", "div.third"]
        result = await wait_for_any_selector(mock_page, selectors, timeout=5000)
        
        assert result is not None
        matched_selector, element = result
        # In parallel execution, any selector can return first
        assert matched_selector in selectors
        assert element == mock_element

    @pytest.mark.asyncio
    async def test_returns_none_when_no_selector_found(self):
        """Test that function returns None when no selector is found."""
        mock_page = AsyncMock()
        
        # All selectors fail
        mock_page.wait_for_selector.side_effect = Exception("Timeout")
        
        selectors = ["div.nonexistent", "div.missing"]
        result = await wait_for_any_selector(mock_page, selectors, timeout=1000)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_correct_timeout(self):
        """Test that function uses the provided timeout."""
        mock_page = AsyncMock()
        mock_element = MagicMock()
        mock_page.wait_for_selector.return_value = mock_element
        
        timeout = 3000
        selectors = ["div.test"]
        
        await wait_for_any_selector(mock_page, selectors, timeout=timeout)
        
        mock_page.wait_for_selector.assert_called_once_with(
            "div.test",
            state="visible",
            timeout=timeout
        )

    @pytest.mark.asyncio
    async def test_uses_correct_state_parameter(self):
        """Test that function uses the provided state parameter."""
        mock_page = AsyncMock()
        mock_element = MagicMock()
        mock_page.wait_for_selector.return_value = mock_element
        
        selectors = ["div.test"]
        state = "attached"
        
        await wait_for_any_selector(mock_page, selectors, state=state)
        
        mock_page.wait_for_selector.assert_called_once_with(
            "div.test",
            state=state,
            timeout=10000  # default timeout
        )

    @pytest.mark.asyncio
    async def test_handles_multiple_selectors(self):
        """Test that function handles multiple selectors correctly."""
        mock_page = AsyncMock()
        mock_element = MagicMock()
        
        # Make first two fail, third succeeds
        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if args[0] == "div.third":
                return mock_element
            raise Exception("Not found")
        
        mock_page.wait_for_selector.side_effect = side_effect
        
        selectors = ["div.first", "div.second", "div.third"]
        result = await wait_for_any_selector(mock_page, selectors, timeout=5000)
        
        assert result is not None
        matched_selector, element = result
        assert matched_selector == "div.third"
        assert element == mock_element


# class TestCheckAnySelectorPresent:
#     """Test suite for check_any_selector_present function."""
#
#     @pytest.mark.asyncio
#     async def test_returns_first_present_selector(self):
#         """Test that function returns the first selector that is present."""
#         mock_page = AsyncMock()
#         mock_elements = [MagicMock(), MagicMock()]
#
#         mock_page.query_selector_all.return_value = mock_elements
#
#         selectors = ["div.first", "div.second"]
#         result = await check_any_selector_present(mock_page, selectors)
#
#         assert result is not None
#         matched_selector, elements = result
#         assert matched_selector == "div.first"
#         assert elements == mock_elements
#
#     @pytest.mark.asyncio
#     async def test_returns_none_when_no_selector_present(self):
#         """Test that function returns None when no selector is present."""
#         mock_page = AsyncMock()
#
#         # All queries return empty list
#         mock_page.query_selector_all.return_value = []
#
#         selectors = ["div.nonexistent", "div.missing"]
#         result = await check_any_selector_present(mock_page, selectors)
#
#         assert result is None
#
#     @pytest.mark.asyncio
#     async def test_tries_all_selectors_until_found(self):
#         """Test that function tries selectors in order until one is found."""
#         mock_page = AsyncMock()
#         mock_elements = [MagicMock()]
#
#         # First call returns empty, second returns elements
#         mock_page.query_selector_all.side_effect = [[], mock_elements]
#
#         selectors = ["div.first", "div.second"]
#         result = await check_any_selector_present(mock_page, selectors)
#
#         assert result is not None
#         matched_selector, elements = result
#         assert matched_selector == "div.second"
#         assert elements == mock_elements
#
#         # Should have called twice
#         assert mock_page.query_selector_all.call_count == 2
#
#     @pytest.mark.asyncio
#     async def test_handles_exceptions_gracefully(self):
#         """Test that function handles exceptions and continues checking."""
#         mock_page = AsyncMock()
#         mock_elements = [MagicMock()]
#
#         # First call raises exception, second succeeds
#         mock_page.query_selector_all.side_effect = [
#             Exception("Error"),
#             mock_elements
#         ]
#
#         selectors = ["div.error", "div.success"]
#         result = await check_any_selector_present(mock_page, selectors)
#
#         assert result is not None
#         matched_selector, elements = result
#         assert matched_selector == "div.success"
#         assert elements == mock_elements
