import pytest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from core.utils import ask_user, wait


class TestAskUser:
    
    @patch('builtins.input', return_value='user_input')
    @patch('builtins.print')
    def test_ask_user_returns_input(self, mock_print, mock_input):
        """Test that ask_user prints the prompt and returns user input."""
        prompt = "Enter your name: "
        result = ask_user(prompt)
        
        mock_print.assert_called_once_with(prompt, end="")
        mock_input.assert_called_once()
        assert result == 'user_input'


class TestWait:
    
    @patch('core.utils.time')
    def test_wait_correct_duration(self, mock_time):
        """Test that wait function sleeps for the correct duration in seconds."""
        time_ms = 2000  # 2 seconds
        
        wait(time_ms)
        
        mock_time.sleep.assert_called_once_with(2.0)  # 2000 ms = 2.0 seconds
    
    @patch('core.utils.time')
    def test_wait_converts_ms_to_seconds(self, mock_time):
        """Test that wait function correctly converts milliseconds to seconds."""
        time_ms = 500  # 0.5 seconds
        
        wait(time_ms)
        
        mock_time.sleep.assert_called_once_with(0.5)  # 500 ms = 0.5 seconds