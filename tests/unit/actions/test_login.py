import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from actions.login import login


class TestLogin:
    
    @pytest.mark.asyncio
    @patch('actions.login.ask_user')
    async def test_login_with_existing_session(self, mock_ask_user):
        """Test login when an active session is already present."""
        mock_page = AsyncMock()
        mock_selector = AsyncMock()
        mock_page.wait_for_selector.return_value = mock_selector
        
        await login(mock_page, "email", "password")
        
        mock_page.wait_for_selector.assert_called_once_with("nav.global-nav", timeout=5000)
        mock_page.goto.assert_called_once_with("https://www.linkedin.com/feed/", wait_until="load")
        # Should not proceed with login steps
        mock_page.type.assert_not_called()
        mock_page.click.assert_not_called()
        mock_ask_user.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('actions.login.ask_user')
    async def test_login_without_existing_session(self, mock_ask_user):
        """Test login when no active session is present."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = TimeoutError()  # No active session
        mock_page.query_selector.return_value = None  # No captcha
        
        await login(mock_page, "test@example.com", "password123")
        
        # First call to check for existing session
        mock_page.wait_for_selector.assert_called_with("nav.global-nav", timeout=5000)
        # Second call after login
        assert mock_page.wait_for_selector.call_count == 1  # Only the first call
        
        # Should proceed with login
        mock_page.goto.assert_any_call("https://www.linkedin.com/login", wait_until="load")
        mock_page.type.assert_any_call("input#username", "test@example.com")
        mock_page.type.assert_any_call("input#password", "password123")
        mock_page.click.assert_called()
        # Should not call ask_user since no captcha is detected
        mock_ask_user.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('actions.login.ask_user')
    async def test_login_with_captcha(self, mock_ask_user):
        """Test login process when captcha is detected."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = TimeoutError()  # No active session
        mock_captcha_element = AsyncMock()
        mock_page.query_selector.return_value = mock_captcha_element  # Captcha detected
        mock_ask_user.return_value = "user_input"
        
        await login(mock_page, "test@example.com", "password123")
        
        # Should call ask_user for captcha
        mock_ask_user.assert_called_once()
        # Should navigate to feed after captcha
        mock_page.goto.assert_any_call("https://www.linkedin.com/feed/", wait_until="load")
    
    @pytest.mark.asyncio
    @patch('actions.login.ask_user')
    async def test_login_skip_button_present(self, mock_ask_user):
        """Test login process when skip button is present after login."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = [TimeoutError(), None] # No session, then element found
        mock_page.query_selector.return_value = None  # No captcha
        
        await login(mock_page, "test@example.com", "password123")
        
        # Should click the skip button
        mock_page.click.assert_called()
    
    @pytest.mark.asyncio
    @patch('actions.login.ask_user')
    async def test_login_skip_button_not_present(self, mock_ask_user):
        """Test login process when skip button is not present after login."""
        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = TimeoutError()  # No session
        mock_page.query_selector.return_value = None  # No captcha, no skip button
        
        await login(mock_page, "test@example.com", "password123")
        
        # Should try to click skip button but handle exception
        mock_page.click.assert_called()