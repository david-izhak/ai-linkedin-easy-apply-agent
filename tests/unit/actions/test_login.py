import pytest
from unittest.mock import AsyncMock, patch, MagicMock, ANY
import sys
import os
from dataclasses import dataclass, field

from actions.login import login
from config import AppConfig, config

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)

# Mock ResilienceExecutor for testing
mock_executor_instance = AsyncMock()

@pytest.fixture(autouse=True)
def mock_get_resilience_executor():
    with patch('actions.login.get_resilience_executor', return_value=mock_executor_instance) as mock:
        # Reset mock's behavior and call history before each test
        mock_executor_instance.reset_mock()
        mock_executor_instance.navigate = AsyncMock()
        mock_executor_instance.wait_for_selector = AsyncMock()
        mock_executor_instance.fill = AsyncMock()
        mock_executor_instance.click = AsyncMock()
        mock_executor_instance.query_selector_with_retry = AsyncMock()
        yield mock


class TestLogin:

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    @patch("actions.login.wait_for_any_selector")
    async def test_login_with_existing_session(self, mock_wait_for_any_selector, mock_ask_user, monkeypatch):
        """Test login when an active session is already present."""
        
        @dataclass
        class MockPerformanceConfig:
            selector_timeout: int = 5000
        
        @dataclass
        class MockConfig:
            performance: MockPerformanceConfig = field(default_factory=MockPerformanceConfig)

        monkeypatch.setattr("actions.login.config", MockConfig())
        
        mock_page = AsyncMock()
        # Mock that we're already on feed page (active session)
        mock_page.url = "https://www.linkedin.com/feed/"
        mock_wait_for_any_selector.return_value = "nav.global-nav"
        mock_executor_instance.query_selector_with_retry.return_value = AsyncMock()

        await login(mock_page)

        # Should only navigate to feed initially (now uses executor.navigate)
        mock_executor_instance.navigate.assert_called_once_with(
            "https://www.linkedin.com/feed/", wait_until="load"
        )
        # Should not proceed with login steps
        mock_executor_instance.fill.assert_not_called()
        mock_ask_user.assert_not_called()

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    @patch("actions.login.wait_for_any_selector")
    async def test_login_without_existing_session(self, mock_wait_for_any_selector, mock_ask_user, monkeypatch):
        """Test login when no active session is present."""
        
        @dataclass
        class MockLoginConfig:
            email: str = "test@example.com"
            password: str = "password123"

        @dataclass
        class MockPerformanceConfig:
            selector_timeout: int = 5000

        @dataclass
        class MockConfig:
            login: MockLoginConfig = field(default_factory=MockLoginConfig)
            performance: MockPerformanceConfig = field(default_factory=MockPerformanceConfig)

        monkeypatch.setattr("actions.login.config", MockConfig())

        mock_page = AsyncMock()
        # Mock that we're redirected to auth page (no active session)
        mock_page.url = "https://www.linkedin.com/authwall"
        # First call returns email_input (no session), second returns login_indicator (after login)
        mock_wait_for_any_selector.side_effect = ["input#username", "nav.global-nav"]
        mock_executor_instance.query_selector_with_retry.return_value = None  # No captcha

        await login(mock_page)

        # Should proceed with login - navigate is called multiple times
        assert mock_executor_instance.navigate.call_count >= 2
        # Check that navigate was called with feed URL
        feed_calls = [call for call in mock_executor_instance.navigate.call_args_list 
                      if call[0][0] == "https://www.linkedin.com/feed/"]
        assert len(feed_calls) >= 1
        # Check that navigate was called with login URL
        login_calls = [call for call in mock_executor_instance.navigate.call_args_list 
                       if call[0][0] == "https://www.linkedin.com/login"]
        assert len(login_calls) >= 1
        # Should fill in credentials
        mock_executor_instance.fill.assert_any_call("email_input", "test@example.com", css_selector=ANY)
        mock_executor_instance.fill.assert_any_call("password_input", "password123", css_selector=ANY)
        # Should click submit
        assert mock_executor_instance.click.call_count >= 1
        # Should not call ask_user since no captcha is detected
        mock_ask_user.assert_not_called()

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    @patch("actions.login.wait_for_any_selector")
    async def test_login_with_captcha(self, mock_wait_for_any_selector, mock_ask_user, monkeypatch):
        """Test login process when captcha is detected."""
        
        @dataclass
        class MockLoginConfig:
            email: str = "test@example.com"
            password: str = "password123"
        
        @dataclass
        class MockPerformanceConfig:
            selector_timeout: int = 5000

        @dataclass
        class MockConfig:
            login: MockLoginConfig = field(default_factory=MockLoginConfig)
            performance: MockPerformanceConfig = field(default_factory=MockPerformanceConfig)

        monkeypatch.setattr("actions.login.config", MockConfig())
        
        mock_page = AsyncMock()
        # Mock that we're redirected to auth page (no active session)
        mock_page.url = "https://www.linkedin.com/authwall"
        # First call returns email_input (no session), second returns captcha
        mock_wait_for_any_selector.side_effect = ["input#username", "div.captcha"]
        mock_captcha_element = AsyncMock()
        mock_executor_instance.query_selector_with_retry.return_value = mock_captcha_element  # Captcha detected
        mock_ask_user.return_value = None

        await login(mock_page)

        # Should call ask_user for captcha
        mock_ask_user.assert_called_once()
        # Should navigate to feed after captcha - appears twice: initially and after captcha
        assert mock_executor_instance.navigate.call_count >= 2
        feed_calls = [call for call in mock_executor_instance.navigate.call_args_list 
                      if call[0][0] == "https://www.linkedin.com/feed/"]
        assert len(feed_calls) >= 1

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    @patch("actions.login.wait_for_any_selector")
    async def test_login_skip_button_present(self, mock_wait_for_any_selector, mock_ask_user, monkeypatch):
        """Test login process when skip button is present after login."""
        
        @dataclass
        class MockLoginConfig:
            email: str = "test@example.com"
            password: str = "password123"
        
        @dataclass
        class MockPerformanceConfig:
            selector_timeout: int = 5000
        
        @dataclass
        class MockConfig:
            login: MockLoginConfig = field(default_factory=MockLoginConfig)
            performance: MockPerformanceConfig = field(default_factory=MockPerformanceConfig)
        
        monkeypatch.setattr("actions.login.config", MockConfig())
        
        mock_page = AsyncMock()
        # Mock that we're redirected to auth page (no active session)
        mock_page.url = "https://www.linkedin.com/authwall"
        # First call returns email_input (no session), second returns login_indicator (after login)
        mock_wait_for_any_selector.side_effect = ["input#username", "nav.global-nav"]
        mock_executor_instance.query_selector_with_retry.return_value = None  # No captcha

        await login(mock_page)

        # Should click buttons (submit + skip) - now uses executor.click
        assert mock_executor_instance.click.call_count >= 1

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    @patch("actions.login.wait_for_any_selector")
    async def test_login_skip_button_not_present(self, mock_wait_for_any_selector, mock_ask_user, monkeypatch):
        """Test login process when skip button is not present after login."""
        
        @dataclass
        class MockLoginConfig:
            email: str = "test@example.com"
            password: str = "password123"

        @dataclass
        class MockPerformanceConfig:
            selector_timeout: int = 5000

        @dataclass
        class MockConfig:
            login: MockLoginConfig = field(default_factory=MockLoginConfig)
            performance: MockPerformanceConfig = field(default_factory=MockPerformanceConfig)

        monkeypatch.setattr("actions.login.config", MockConfig())
        
        mock_page = AsyncMock()
        # Mock that we're redirected to auth page (no active session)
        mock_page.url = "https://www.linkedin.com/authwall"
        # First call returns email_input (no session), second returns login_indicator (after login)
        mock_wait_for_any_selector.side_effect = ["input#username", "nav.global-nav"]
        mock_executor_instance.query_selector_with_retry.return_value = None  # No captcha
        # Make skip button click throw an exception
        def click_side_effect(*args, **kwargs):
            if "skip" in str(args) or "dismiss" in str(args):
                raise Exception("Skip button not found")
        mock_executor_instance.click.side_effect = click_side_effect

        await login(mock_page)

        # Should try to click button (at least submit) - now uses executor.click
        assert mock_executor_instance.click.call_count >= 1
