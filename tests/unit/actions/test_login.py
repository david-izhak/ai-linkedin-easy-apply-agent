import pytest
from unittest.mock import AsyncMock, patch
import sys
import os
from dataclasses import dataclass, field

from actions.login import login
from config import AppConfig, config

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
)


class TestLogin:

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    async def test_login_with_existing_session(self, mock_ask_user, monkeypatch):
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
        mock_nav = AsyncMock()
        mock_page.query_selector.return_value = mock_nav

        await login(mock_page)

        # Should only navigate to feed initially
        mock_page.goto.assert_called_once_with(
            "https://www.linkedin.com/feed/", wait_until="load"
        )
        # Should not proceed with login steps
        mock_page.fill.assert_not_called()
        mock_ask_user.assert_not_called()

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    async def test_login_without_existing_session(self, mock_ask_user, monkeypatch):
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
        mock_page.query_selector.return_value = None  # No captcha

        await login(mock_page)

        # Should proceed with login
        assert mock_page.goto.call_count >= 2
        mock_page.goto.assert_any_call(
            "https://www.linkedin.com/feed/", wait_until="load"
        )
        mock_page.goto.assert_any_call(
            "https://www.linkedin.com/login", wait_until="load"
        )
        # Should fill in credentials
        mock_page.fill.assert_any_call("input#username", "test@example.com")
        mock_page.fill.assert_any_call("input#password", "password123")
        # Should click submit
        assert mock_page.click.call_count >= 1
        # Should not call ask_user since no captcha is detected
        mock_ask_user.assert_not_called()

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    async def test_login_with_captcha(self, mock_ask_user, monkeypatch):
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
        mock_captcha_element = AsyncMock()
        mock_page.query_selector.return_value = mock_captcha_element  # Captcha detected
        mock_ask_user.return_value = None

        await login(mock_page)

        # Should call ask_user for captcha
        mock_ask_user.assert_called_once()
        # Should navigate to feed after captcha - appears twice: initially and after captcha
        assert mock_page.goto.call_count >= 2
        feed_calls = [call for call in mock_page.goto.call_args_list 
                      if call[0][0] == "https://www.linkedin.com/feed/"]
        assert len(feed_calls) >= 1

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    async def test_login_skip_button_present(self, mock_ask_user, monkeypatch):
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
        mock_page.query_selector.return_value = None  # No captcha

        await login(mock_page)

        # Should click buttons (submit + skip)
        assert mock_page.click.call_count >= 1

    @pytest.mark.asyncio
    @patch("actions.login.ask_user")
    async def test_login_skip_button_not_present(self, mock_ask_user, monkeypatch):
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
        mock_page.query_selector.return_value = None  # No captcha
        # Make skip button click throw an exception
        async def click_side_effect(selector, **kwargs):
            if "skip" in selector or "dismiss" in selector:
                raise Exception("Skip button not found")
        mock_page.click.side_effect = click_side_effect

        await login(mock_page)

        # Should try to click button (at least submit)
        assert mock_page.click.call_count >= 1
