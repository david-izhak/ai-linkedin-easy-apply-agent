"""Unit tests for main.py functions."""

import pytest
from main import get_submit_mode_from_bot_mode, validate_bot_mode


class TestGetSubmitModeFromBotMode:
    """Tests for get_submit_mode_from_bot_mode function."""

    def test_processing_submit_returns_true(self) -> None:
        """Test that processing_submit mode returns True."""
        result = get_submit_mode_from_bot_mode("processing_submit")
        assert result is True

    def test_full_run_submit_returns_true(self) -> None:
        """Test that full_run_submit mode returns True."""
        result = get_submit_mode_from_bot_mode("full_run_submit")
        assert result is True

    def test_processing_returns_false(self) -> None:
        """Test that processing mode returns False (DRY RUN)."""
        result = get_submit_mode_from_bot_mode("processing")
        assert result is False

    def test_full_run_returns_false(self) -> None:
        """Test that full_run mode returns False (DRY RUN)."""
        result = get_submit_mode_from_bot_mode("full_run")
        assert result is False

    def test_discovery_returns_false(self) -> None:
        """Test that discovery mode returns False."""
        result = get_submit_mode_from_bot_mode("discovery")
        assert result is False

    def test_enrichment_returns_false(self) -> None:
        """Test that enrichment mode returns False."""
        result = get_submit_mode_from_bot_mode("enrichment")
        assert result is False

    def test_test_logging_returns_false(self) -> None:
        """Test that test_logging mode returns False."""
        result = get_submit_mode_from_bot_mode("test_logging")
        assert result is False


class TestValidateBotMode:
    """Tests for validate_bot_mode function."""

    def test_valid_mode_discovery(self) -> None:
        """Test that discovery mode is valid and doesn't raise."""
        valid_modes = [
            "discovery",
            "enrichment",
            "processing",
            "processing_submit",
            "full_run",
            "full_run_submit",
            "test_logging",
        ]
        # Should not raise
        validate_bot_mode("discovery", valid_modes)

    def test_valid_mode_processing_submit(self) -> None:
        """Test that processing_submit mode is valid and doesn't raise."""
        valid_modes = [
            "discovery",
            "enrichment",
            "processing",
            "processing_submit",
            "full_run",
            "full_run_submit",
            "test_logging",
        ]
        # Should not raise
        validate_bot_mode("processing_submit", valid_modes)

    def test_valid_mode_full_run_submit(self) -> None:
        """Test that full_run_submit mode is valid and doesn't raise."""
        valid_modes = [
            "discovery",
            "enrichment",
            "processing",
            "processing_submit",
            "full_run",
            "full_run_submit",
            "test_logging",
        ]
        # Should not raise
        validate_bot_mode("full_run_submit", valid_modes)

    def test_invalid_mode_raises_value_error(self) -> None:
        """Test that invalid mode raises ValueError."""
        valid_modes = [
            "discovery",
            "enrichment",
            "processing",
            "processing_submit",
            "full_run",
            "full_run_submit",
            "test_logging",
        ]
        with pytest.raises(
            ValueError, match="Invalid BOT_MODE: 'invalid_mode'. Valid modes are:"
        ):
            validate_bot_mode("invalid_mode", valid_modes)

    def test_invalid_mode_error_message_contains_valid_modes(self) -> None:
        """Test that error message contains list of valid modes."""
        valid_modes = ["discovery", "processing"]
        with pytest.raises(ValueError) as exc_info:
            validate_bot_mode("wrong_mode", valid_modes)

        error_message = str(exc_info.value)
        assert "discovery" in error_message
        assert "processing" in error_message
        assert "wrong_mode" in error_message

    def test_empty_mode_raises_value_error(self) -> None:
        """Test that empty mode string raises ValueError."""
        valid_modes = ["discovery", "processing"]
        with pytest.raises(ValueError):
            validate_bot_mode("", valid_modes)

    def test_case_sensitive_validation(self) -> None:
        """Test that mode validation is case-sensitive."""
        valid_modes = ["discovery", "processing"]
        with pytest.raises(ValueError):
            validate_bot_mode("DISCOVERY", valid_modes)  # Uppercase should fail
