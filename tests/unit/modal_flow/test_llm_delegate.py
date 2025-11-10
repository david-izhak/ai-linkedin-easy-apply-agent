"""Unit tests for LLMDelegate and RuleSuggestion."""

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, AsyncMock, patch

from modal_flow.llm_delegate import RuleSuggestion, LLMDecision, StrategyDefinition
from modal_flow.llm_delegate_openai import OpenAILLMDelegate
from modal_flow.profile_schema import CandidateProfile


class TestRuleSuggestion:
    """Tests for RuleSuggestion model."""
    
    def test_rule_suggestion_valid(self):
        """Test RuleSuggestion with valid data."""
        rule = RuleSuggestion(
            q_pattern="(python|питон)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.9
        )
        assert rule.q_pattern == "(python|питон)"
        assert isinstance(rule.strategy, StrategyDefinition)
        assert rule.strategy.kind == "literal"
        assert rule.strategy.params == {"value": True}
        assert rule.confidence == 0.9
    
    def test_rule_suggestion_confidence_bounds(self):
        """Test RuleSuggestion confidence bounds validation."""
        # Valid confidence values
        RuleSuggestion(
            q_pattern="test",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.0
        )
        RuleSuggestion(
            q_pattern="test",
            strategy={"kind": "literal", "params": {"value": False}},
            confidence=1.0
        )
        RuleSuggestion(
            q_pattern="test",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.85
        )
        
        # Invalid confidence values
        with pytest.raises(ValidationError):
            RuleSuggestion(
                q_pattern="test",
                strategy={"kind": "literal", "params": {"value": True}},
                confidence=-0.1
            )
        
        with pytest.raises(ValidationError):
            RuleSuggestion(
                q_pattern="test",
                strategy={"kind": "literal", "params": {"value": True}},
                confidence=1.1
            )
        
        # Test that empty params are rejected
        with pytest.raises(ValidationError):
            RuleSuggestion(
                q_pattern="test",
                strategy={"kind": "literal", "params": {}},
                confidence=0.9
            )
    
    def test_rule_suggestion_missing_fields(self):
        """Test RuleSuggestion with missing required fields."""
        with pytest.raises(ValidationError):
            RuleSuggestion(
                q_pattern="test",
                strategy={"kind": "literal"}
            )
        
        with pytest.raises(ValidationError):
            RuleSuggestion(
                strategy={"kind": "literal", "params": {}},
                confidence=0.9
            )
        
        with pytest.raises(ValidationError):
            RuleSuggestion(
                q_pattern="test",
                confidence=0.9
            )
    
    def test_rule_suggestion_strategy_structure(self):
        """Test RuleSuggestion with different strategy structures."""
        # Literal strategy
        rule1 = RuleSuggestion(
            q_pattern="(python)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.9
        )
        assert isinstance(rule1.strategy, StrategyDefinition)
        assert rule1.strategy.kind == "literal"
        assert rule1.strategy.params == {"value": True}
        
        # Profile key strategy
        rule2 = RuleSuggestion(
            q_pattern="(city|город)",
            strategy={"kind": "profile_key", "params": {"key": "address.city"}},
            confidence=0.85
        )
        assert isinstance(rule2.strategy, StrategyDefinition)
        assert rule2.strategy.kind == "profile_key"
        assert rule2.strategy.params == {"key": "address.city"}
        
        # Numeric from profile strategy
        rule3 = RuleSuggestion(
            q_pattern="(years? of experience.*python)",
            strategy={"kind": "numeric_from_profile", "params": {"key": "years_experience.python"}},
            confidence=0.9
        )
        assert isinstance(rule3.strategy, StrategyDefinition)
        assert rule3.strategy.kind == "numeric_from_profile"
        assert rule3.strategy.params == {"key": "years_experience.python"}
        
        # One of options strategy
        rule4 = RuleSuggestion(
            q_pattern="(relocate|готовность к переезду)",
            strategy={"kind": "one_of_options", "params": {"preferred": ["Yes", "Да"]}},
            confidence=0.8
        )
        assert isinstance(rule4.strategy, StrategyDefinition)
        assert rule4.strategy.kind == "one_of_options"
        assert rule4.strategy.params == {"preferred": ["Yes", "Да"]}


class TestOpenAILLMDelegateGenerateRule:
    """Tests for generate_rule() method in OpenAILLMDelegate."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        mock_client = MagicMock()
        return mock_client
    
    @pytest.fixture
    def llm_delegate(self, mock_llm_client):
        """Create OpenAILLMDelegate instance with mocked client."""
        return OpenAILLMDelegate(mock_llm_client)
    
    @pytest.fixture
    def sample_profile(self):
        """Create a sample candidate profile."""
        return CandidateProfile(
            personal={"firstName": "John", "lastName": "Doe"},
            address={"city": "Tel Aviv", "country": "Israel"},
            email="john.doe@example.com",
            phone="+972501234567"
        )
    
    @pytest.fixture
    def sample_field_info(self):
        """Create sample field information."""
        return {
            "question": "Do you know Python?",
            "field_type": "checkbox",
            "options": None,
            "required": True
        }
    
    @pytest.mark.asyncio
    async def test_generate_rule_success(self, llm_delegate, mock_llm_client, sample_profile, sample_field_info):
        """Test successful rule generation."""
        # Mock the LLM client response
        expected_rule = RuleSuggestion(
            q_pattern="(python|питон)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.9
        )
        mock_llm_client.generate_structured_response = MagicMock(return_value=expected_rule)
        
        # Generate rule
        result = await llm_delegate.generate_rule(
            field_info=sample_field_info,
            selected_value=True,
            profile=sample_profile,
            job_context=None
        )
        
        # Verify result
        assert result is not None
        assert result.q_pattern == "(python|питон)"
        assert isinstance(result.strategy, StrategyDefinition)
        assert result.strategy.kind == "literal"
        assert result.confidence == 0.9
        
        # Verify LLM client was called correctly
        mock_llm_client.generate_structured_response.assert_called_once()
        call_args = mock_llm_client.generate_structured_response.call_args
        assert call_args[0][1] == RuleSuggestion  # schema
        assert "RULE_GENERATION_PROMPT" in str(call_args[0][2]) or call_args[0][2] is not None  # system prompt
    
    @pytest.mark.asyncio
    async def test_generate_rule_error_handling(self, llm_delegate, mock_llm_client, sample_profile, sample_field_info):
        """Test error handling in rule generation with client-side fallback."""
        # Mock the LLM client to raise an exception
        mock_llm_client.generate_structured_response = MagicMock(side_effect=Exception("LLM error"))
        
        # Generate rule should fall back to client-side generation
        result = await llm_delegate.generate_rule(
            field_info=sample_field_info,
            selected_value=True,
            profile=sample_profile,
            job_context=None
        )
        
        # Should return a rule generated client-side (checkbox -> literal strategy)
        assert result is not None
        assert isinstance(result.strategy, StrategyDefinition)
        assert result.strategy.kind == "literal"
        assert result.strategy.params == {"value": True}
        assert result.confidence == 0.7  # Lower confidence for client-generated rules
    
    @pytest.mark.asyncio
    async def test_generate_rule_prompt_building(self, llm_delegate, mock_llm_client, sample_profile):
        """Test that prompt is built correctly with all necessary data."""
        field_info = {
            "question": "Location (city)",
            "field_type": "text",
            "options": None,
            "required": True,
            "min": 3,
            "max": 100
        }
        
        expected_rule = RuleSuggestion(
            q_pattern="(location.*city|city|город)",
            strategy={"kind": "profile_key", "params": {"key": "address.city"}},
            confidence=0.9
        )
        mock_llm_client.generate_structured_response = MagicMock(return_value=expected_rule)
        
        # Generate rule
        await llm_delegate.generate_rule(
            field_info=field_info,
            selected_value="Tel Aviv",
            profile=sample_profile,
            job_context=None
        )
        
        # Verify prompt was built with field info
        call_args = mock_llm_client.generate_structured_response.call_args
        user_prompt = call_args[0][0]
        assert "Location (city)" in user_prompt
        assert "text" in user_prompt
        assert "Tel Aviv" in user_prompt
        assert "min=3" in user_prompt
        assert "max=100" in user_prompt
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("field_type,question,selected_value,expected_strategy_kind", [
        ("checkbox", "Do you know Python?", True, "literal"),
        ("text", "What is your email?", "test@example.com", "profile_key"),
        ("number", "Years of experience with Python", 5, "numeric_from_profile"),
        ("radio", "Willing to relocate?", "Yes", "one_of_options"),
        ("select", "Choose an option", "option1", "one_of_options"),
        ("combobox", "Location (city)", "Tel Aviv, Israel", "profile_key"),
    ])
    async def test_generate_rule_different_field_types(
        self, llm_delegate, mock_llm_client, sample_profile, field_type, question, selected_value, expected_strategy_kind
    ):
        """Test rule generation for different field types.
        
        This test verifies that when LLM returns a rule with empty params (as a dict),
        the client-side generation fills in the required params.
        """
        field_info = {
            "question": question,
            "field_type": field_type,
            "options": ["Yes", "No"] if field_type in ["radio", "select"] else None,
            "required": True
        }
        
        # Mock LLM returning rule as dict with empty params (simulating the problem we're fixing)
        # The client-side generation should fill in the params before validation
        mock_rule_dict = {
            "q_pattern": f"({field_type})",
            "strategy": {"kind": expected_strategy_kind, "params": {}},
            "confidence": 0.9
        }
        mock_llm_client.generate_structured_response = MagicMock(return_value=mock_rule_dict)
        
        result = await llm_delegate.generate_rule(
            field_info=field_info,
            selected_value=selected_value,
            profile=sample_profile,
            job_context=None
        )
        
        assert result is not None, f"Rule generation failed for {field_type} with question '{question}'"
        assert isinstance(result.strategy, StrategyDefinition)
        assert result.strategy.kind == expected_strategy_kind
        # Client-side generation should have filled in the params
        assert result.strategy.params is not None
        assert len(result.strategy.params) > 0, f"Params should not be empty for {expected_strategy_kind}. Got: {result.strategy.params}"
    
    @pytest.mark.asyncio
    async def test_generate_rule_with_job_context(self, llm_delegate, mock_llm_client, sample_profile, sample_field_info):
        """Test rule generation with job context."""
        job_context = {
            "title": "Software Engineer",
            "company": "Tech Corp",
            "description": "Python developer position"
        }
        
        expected_rule = RuleSuggestion(
            q_pattern="(python)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.9
        )
        mock_llm_client.generate_structured_response = MagicMock(return_value=expected_rule)
        
        await llm_delegate.generate_rule(
            field_info=sample_field_info,
            selected_value=True,
            profile=sample_profile,
            job_context=job_context
        )
        
        # Verify job context was included in prompt
        call_args = mock_llm_client.generate_structured_response.call_args
        user_prompt = call_args[0][0]
        assert "JOB CONTEXT" in user_prompt
        assert "Software Engineer" in user_prompt
    
    @pytest.mark.asyncio
    async def test_generate_rule_with_options(self, llm_delegate, mock_llm_client, sample_profile):
        """Test rule generation for fields with options."""
        field_info = {
            "question": "Willing to relocate?",
            "field_type": "radio",
            "options": ["Yes", "No", "Maybe"],
            "required": True
        }
        
        expected_rule = RuleSuggestion(
            q_pattern="(relocate|готовность к переезду)",
            strategy={"kind": "one_of_options", "params": {"preferred": ["Yes", "Да"]}},
            confidence=0.85
        )
        mock_llm_client.generate_structured_response = MagicMock(return_value=expected_rule)
        
        result = await llm_delegate.generate_rule(
            field_info=field_info,
            selected_value="Yes",
            profile=sample_profile,
            job_context=None
        )
        
        assert result is not None
        # Verify options were included in prompt
        call_args = mock_llm_client.generate_structured_response.call_args
        user_prompt = call_args[0][0]
        assert "Yes, No, Maybe" in user_prompt
    
    @pytest.mark.asyncio
    async def test_generate_rule_empty_strategy_fallback(self, llm_delegate, mock_llm_client, sample_profile):
        """Test that empty strategy from LLM triggers client-side generation."""
        field_info = {
            "question": "Do you know Python?",
            "field_type": "checkbox",
            "options": None,
            "required": True
        }
        
        # Simulate LLM returning dict with empty strategy (like in logs)
        # This simulates the actual case from logs where LLM returns:
        # {"q_pattern": "...", "strategy": {}, "confidence": 0.95}
        llm_response_dict = {
            "q_pattern": "(python|питон)",
            "strategy": {},  # Empty dict - this is the problem from logs
            "confidence": 0.95
        }
        mock_llm_client.generate_structured_response = MagicMock(return_value=llm_response_dict)
        
        result = await llm_delegate.generate_rule(
            field_info=field_info,
            selected_value=True,
            profile=sample_profile,
            job_context=None
        )
        
        # Should fall back to client-side strategy generation
        assert result is not None
        assert isinstance(result.strategy, StrategyDefinition)
        assert result.strategy.kind == "literal"  # Client-side generated
        assert result.strategy.params == {"value": True}
        assert result.q_pattern == "(python|питон)"  # Keep LLM pattern
        assert result.confidence == 0.95  # Keep LLM confidence

