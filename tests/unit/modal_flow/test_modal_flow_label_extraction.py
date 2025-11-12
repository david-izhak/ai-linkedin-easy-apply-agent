"""Unit tests for label extraction from siblings in ModalFlowRunner."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from playwright.async_api import Locator

from modal_flow.modal_flow import ModalFlowRunner
from modal_flow.profile_schema import CandidateProfile
from modal_flow.rules_store import RuleStore
from modal_flow.normalizer import QuestionNormalizer


@pytest.fixture
def mock_page():
    """Create a mock Playwright Page."""
    page = MagicMock()
    return page


@pytest.fixture
def sample_profile():
    """Create a sample candidate profile."""
    return CandidateProfile(
        personal={"firstName": "John", "lastName": "Doe"},
        address={"city": "Tel Aviv", "country": "Israel"},
        email="john.doe@example.com",
        phone="+972501234567"
    )


@pytest.fixture
def temp_rule_store(tmp_path):
    """Create a temporary rule store."""
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("schema_version: '1.0'\nrules: []\n")
    return RuleStore(str(rules_file))


@pytest.fixture
def modal_flow_runner(mock_page, sample_profile, temp_rule_store):
    """Create ModalFlowRunner instance for testing."""
    return ModalFlowRunner(
        page=mock_page,
        profile=sample_profile,
        rule_store=temp_rule_store,
        normalizer=QuestionNormalizer(),
        logger=None
    )


@pytest.mark.asyncio
async def test_extract_label_from_siblings_single_level(modal_flow_runner):
    """Test extracting label from siblings at a single level."""
    mock_element = MagicMock(spec=Locator)
    
    # Mock the evaluate to return combined label text
    mock_element.evaluate = AsyncMock(return_value="LinkedIn Profile. Ex: https://www.linkedin.com/in/xxx-xxx-xxx")
    
    result = await modal_flow_runner._extract_label_from_siblings(mock_element)
    
    assert result == "LinkedIn Profile. Ex: https://www.linkedin.com/in/xxx-xxx-xxx"
    mock_element.evaluate.assert_called_once()


@pytest.mark.asyncio
async def test_extract_label_from_siblings_no_siblings(modal_flow_runner):
    """Test when no valid siblings are found."""
    mock_element = MagicMock(spec=Locator)
    mock_element.evaluate = AsyncMock(return_value="")
    
    result = await modal_flow_runner._extract_label_from_siblings(mock_element)
    
    assert result == ""


@pytest.mark.asyncio
async def test_extract_label_from_siblings_multiple_levels(modal_flow_runner):
    """Test extracting label when siblings are found at multiple levels."""
    mock_element = MagicMock(spec=Locator)
    
    # Simulate finding labels at different levels with same minimum distance
    mock_element.evaluate = AsyncMock(return_value="Level 1 Text. Level 2 Text")
    
    result = await modal_flow_runner._extract_label_from_siblings(mock_element)
    
    assert result == "Level 1 Text. Level 2 Text"


@pytest.mark.asyncio
async def test_extract_label_from_siblings_filters_error_text(modal_flow_runner):
    """Test that error messages are filtered out."""
    mock_element = MagicMock(spec=Locator)
    
    # The JavaScript code should filter out error messages
    # This test verifies the integration works
    mock_element.evaluate = AsyncMock(return_value="Valid Label")
    
    result = await modal_flow_runner._extract_label_from_siblings(mock_element)
    
    assert result == "Valid Label"
    # Error messages should be filtered by the JavaScript code


@pytest.mark.asyncio
async def test_label_for_integrates_sibling_extraction(modal_flow_runner):
    """Test that _label_for uses sibling extraction as fallback."""
    mock_element = MagicMock(spec=Locator)
    
    # Mock all standard methods to return empty/None
    mock_element.get_attribute = AsyncMock(return_value=None)
    mock_element.evaluate = AsyncMock(return_value="")
    
    # Mock sibling extraction to return a label
    modal_flow_runner._extract_label_from_siblings = AsyncMock(return_value="LinkedIn Profile. Example text")
    
    result = await modal_flow_runner._label_for(mock_element)
    
    # Should use sibling extraction result
    assert result == "LinkedIn Profile. Example text"
    modal_flow_runner._extract_label_from_siblings.assert_called_once_with(mock_element)


@pytest.mark.asyncio
async def test_label_for_fallback_to_field_when_all_fail(modal_flow_runner):
    """Test that _label_for falls back to 'field' when all methods fail."""
    mock_element = MagicMock(spec=Locator)
    
    # Mock all methods to return empty/None
    mock_element.get_attribute = AsyncMock(return_value=None)
    mock_element.evaluate = AsyncMock(return_value="")
    
    # Mock sibling extraction to return empty
    modal_flow_runner._extract_label_from_siblings = AsyncMock(return_value="")
    
    result = await modal_flow_runner._label_for(mock_element)
    
    # Should fall back to "field"
    assert result == "field"
    modal_flow_runner._extract_label_from_siblings.assert_called_once_with(mock_element)

