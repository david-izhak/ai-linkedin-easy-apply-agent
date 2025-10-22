"""Unit tests for the QuestionNormalizer class."""

import pytest
from modal_flow.normalizer import QuestionNormalizer


@pytest.fixture
def normalizer() -> QuestionNormalizer:
    """Fixture for QuestionNormalizer."""
    return QuestionNormalizer()


class TestNormalizeString:
    """Tests for the normalize_string method."""

    @pytest.mark.parametrize(
        "input_str, expected_str",
        [
            ("  hello world  ", "hello world"),
            ("hello   world", "hello world"),
            ("\t a \n b \t", "a b"),
            ("  multiple   spaces  ", "multiple spaces"),
            ("no_spaces", "no_spaces"),
            ("", ""),
            ("  ", ""),
        ],
    )
    def test_various_whitespace_scenarios(
        self, normalizer: QuestionNormalizer, input_str: str, expected_str: str
    ):
        """Test that various whitespace scenarios are handled correctly."""
        assert normalizer.normalize_string(input_str) == expected_str

    def test_non_string_input(self, normalizer: QuestionNormalizer):
        """Test that non-string input is handled gracefully."""
        assert normalizer.normalize_string(None) == ""
        assert normalizer.normalize_string(123) == ""
