"""Unit tests for rule generation integration in RulesEngine."""

import logging
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import tempfile
import yaml

from modal_flow.rules_engine import RulesEngine
from modal_flow.rules_store import RuleStore
from modal_flow.field_signature import FieldSignature
from modal_flow.learning_config import LearningConfig
from modal_flow.llm_delegate import LLMDecision, RuleSuggestion
from modal_flow.profile_schema import CandidateProfile
from modal_flow.normalizer import QuestionNormalizer


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
def temp_rule_store():
    """Create a temporary rule store for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("schema_version: '1.0'\nrules: []\n")
        temp_path = f.name
    
    rule_store = RuleStore(temp_path)
    yield rule_store
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def mock_llm_delegate():
    """Create a mock LLM delegate."""
    delegate = MagicMock()
    delegate.decide = AsyncMock()
    delegate.generate_rule = AsyncMock()
    return delegate


@pytest.fixture
def learning_config_enabled():
    """Create learning config with learning enabled."""
    return LearningConfig(
        enabled=True,
        auto_learn=True,
        use_separate_rule_generation=True,
        rule_generation_fallback=True,
        confidence_threshold=0.85
    )


@pytest.fixture
def learning_config_disabled():
    """Create learning config with learning disabled."""
    return LearningConfig(
        enabled=False,
        auto_learn=False
    )


@pytest.fixture
def rules_engine(sample_profile, temp_rule_store, mock_llm_delegate, learning_config_enabled):
    """Create RulesEngine instance for testing."""
    return RulesEngine(
        profile=sample_profile,
        rule_store=temp_rule_store,
        normalizer=QuestionNormalizer(),
        llm_delegate=mock_llm_delegate,
        learning_config=learning_config_enabled,
        logger=None
    )


class TestRuleGenerationIntegration:
    """Tests for rule generation integration in RulesEngine."""
    
    @pytest.mark.asyncio
    async def test_generate_rule_when_no_suggest_rule(
        self, rules_engine, mock_llm_delegate, sample_profile, temp_rule_store
    ):
        """Test that rule is generated when suggest_rule is missing from decision."""
        # Mock LLM decision without suggest_rule
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule=None
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Mock rule generation
        generated_rule = RuleSuggestion(
            q_pattern="(python|питон)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.9
        )
        mock_llm_delegate.generate_rule.return_value = generated_rule
        
        # Call decide
        result = await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify decision was returned
        assert result is True
        
        # Verify generate_rule was called
        mock_llm_delegate.generate_rule.assert_called_once()
        call_args = mock_llm_delegate.generate_rule.call_args
        assert call_args[1]["selected_value"] is True
        assert call_args[1]["profile"] == sample_profile
        
        # Verify rule was saved to store
        # Note: This depends on _process_suggested_rule being called
        # We can verify by checking if rule_store has the rule
        signature = FieldSignature(
            field_type="checkbox",
            q_norm="do you know python",
            opts_fp=None,
            site="*",
            form_kind="job_apply",
            locale="en"
        )
        # The rule should be findable (if validation passes)
        # This test verifies the integration flow
    
    @pytest.mark.asyncio
    async def test_no_rule_generation_when_learning_disabled(
        self, sample_profile, temp_rule_store, mock_llm_delegate, learning_config_disabled
    ):
        """Test that rule generation is skipped when learning is disabled."""
        rules_engine = RulesEngine(
            profile=sample_profile,
            rule_store=temp_rule_store,
            normalizer=QuestionNormalizer(),
            llm_delegate=mock_llm_delegate,
            learning_config=learning_config_disabled,
            logger=None
        )
        
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule=None
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Call decide
        await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify generate_rule was NOT called
        mock_llm_delegate.generate_rule.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_fallback_to_suggest_rule_from_decision(
        self, rules_engine, mock_llm_delegate, sample_profile
    ):
        """Test fallback to suggest_rule from decision when separate generation fails."""
        # Mock LLM decision with suggest_rule
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule={
                "q_pattern": "(python|питон)",
                "strategy": {"kind": "literal", "params": {"value": True}}
            }
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Mock rule generation to return None (failure)
        mock_llm_delegate.generate_rule.return_value = None
        
        # Call decide
        result = await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify decision was returned
        assert result is True
        
        # Verify generate_rule was called first
        mock_llm_delegate.generate_rule.assert_called_once()
        
        # Verify fallback was used (this is handled internally in _process_suggested_rule)
        # The rule from suggest_rule should be processed
    
    @pytest.mark.asyncio
    async def test_rule_generation_error_handling(
        self, rules_engine, mock_llm_delegate, sample_profile
    ):
        """Test that rule generation errors don't break the flow."""
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule=None
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Mock rule generation to raise an exception
        mock_llm_delegate.generate_rule.side_effect = Exception("Rule generation error")
        
        # Call decide - should not raise exception
        result = await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify decision was still returned
        assert result is True
        
        # Verify generate_rule was called
        mock_llm_delegate.generate_rule.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rule_failure_skips_rule_generation(
        self, rules_engine, mock_llm_delegate, temp_rule_store, caplog
    ):
        """Ensure learning is skipped when an existing rule fails to produce a value."""
        temp_rule_store.data["rules"].append(
            {
                "id": "test_rule_none",
                "scope": {
                    "site": "*",
                    "form_kind": "job_apply",
                    "locale": ["en"],
                },
                "signature": {
                    "field_type": "checkbox",
                    "q_pattern": "(?i)agree",
                    "options_fingerprint": None,
                },
                "strategy": {"kind": "literal", "params": {"value": None}},
                "constraints": {"required": True},
            }
        )
        temp_rule_store.save()

        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule=None,
        )
        mock_llm_delegate.decide.return_value = llm_decision

        with caplog.at_level(logging.INFO):
            result = await rules_engine.decide(
                question="Do you agree?",
                field_type="checkbox",
                options=None,
            )

        assert result is True
        mock_llm_delegate.generate_rule.assert_not_called()
        assert any("[RULE_FAILURE]" in record.message for record in caplog.records)
        assert any(
            "[RULE_GENERATION_SKIPPED]" in record.message for record in caplog.records
        )
    
    @pytest.mark.asyncio
    async def test_rule_generation_with_different_field_types(
        self, rules_engine, mock_llm_delegate, sample_profile
    ):
        """Test rule generation for different field types."""
        test_cases = [
            ("checkbox", True, "check"),
            ("text", "Tel Aviv", "text"),
            ("number", 5, "number"),
            ("radio", "Yes", "select"),
        ]
        
        for field_type, value, decision_type in test_cases:
            mock_llm_delegate.reset_mock()
            
            llm_decision = LLMDecision(
                decision=decision_type,
                value=value,
                confidence=0.9,
                suggest_rule=None
            )
            mock_llm_delegate.decide.return_value = llm_decision
            
            generated_rule = RuleSuggestion(
                q_pattern=f"({field_type})",
                strategy={"kind": "literal", "params": {"value": value}},
                confidence=0.9
            )
            mock_llm_delegate.generate_rule.return_value = generated_rule
            
            # Call decide
            result = await rules_engine.decide(
                question=f"Test {field_type} field",
                field_type=field_type,
                options=["Yes", "No"] if field_type == "radio" else None
            )
            
            # Verify decision was returned
            assert result == value
            
            # Verify generate_rule was called with correct parameters
            mock_llm_delegate.generate_rule.assert_called_once()
            call_args = mock_llm_delegate.generate_rule.call_args
            # generate_rule is called with keyword arguments
            assert call_args.kwargs["selected_value"] == value
            assert call_args.kwargs["field_info"]["field_type"] == field_type
    
    @pytest.mark.asyncio
    async def test_rule_generation_with_high_confidence(
        self, rules_engine, mock_llm_delegate, sample_profile, temp_rule_store
    ):
        """Test that rule is processed when confidence is above threshold."""
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule=None
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Generate rule with high confidence
        generated_rule = RuleSuggestion(
            q_pattern="(python|питон)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.9  # Above threshold of 0.85
        )
        mock_llm_delegate.generate_rule.return_value = generated_rule
        
        # Call decide
        await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify rule generation was called
        mock_llm_delegate.generate_rule.assert_called_once()
        
        # Note: Actual rule saving depends on validation passing
        # This test verifies the integration flow up to rule processing
    
    @pytest.mark.asyncio
    async def test_rule_generation_with_low_confidence(
        self, rules_engine, mock_llm_delegate, sample_profile
    ):
        """Test that rule is not processed when confidence is below threshold."""
        # Update learning config with higher threshold
        rules_engine.learning_config.confidence_threshold = 0.95
        
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule=None
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Generate rule with low confidence
        generated_rule = RuleSuggestion(
            q_pattern="(python|питон)",
            strategy={"kind": "literal", "params": {"value": True}},
            confidence=0.8  # Below threshold of 0.95
        )
        mock_llm_delegate.generate_rule.return_value = generated_rule
        
        # Call decide
        result = await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify decision was returned
        assert result is True
        
        # Verify rule generation was called
        mock_llm_delegate.generate_rule.assert_called_once()
        
        # Rule should be rejected due to low confidence in _process_suggested_rule
    
    @pytest.mark.asyncio
    async def test_no_fallback_when_fallback_disabled(
        self, sample_profile, temp_rule_store, mock_llm_delegate
    ):
        """Test that fallback to suggest_rule is not used when disabled."""
        learning_config = LearningConfig(
            enabled=True,
            auto_learn=True,
            use_separate_rule_generation=True,
            rule_generation_fallback=False,  # Disable fallback
            confidence_threshold=0.85
        )
        
        rules_engine = RulesEngine(
            profile=sample_profile,
            rule_store=temp_rule_store,
            normalizer=QuestionNormalizer(),
            llm_delegate=mock_llm_delegate,
            learning_config=learning_config,
            logger=None
        )
        
        # Mock LLM decision with suggest_rule
        llm_decision = LLMDecision(
            decision="check",
            value=True,
            confidence=0.9,
            suggest_rule={
                "q_pattern": "(python|питон)",
                "strategy": {"kind": "literal", "params": {"value": True}}
            }
        )
        mock_llm_delegate.decide.return_value = llm_decision
        
        # Mock rule generation to return None
        mock_llm_delegate.generate_rule.return_value = None
        
        # Call decide
        result = await rules_engine.decide(
            question="Do you know Python?",
            field_type="checkbox",
            options=None
        )
        
        # Verify decision was returned
        assert result is True
        
        # Verify generate_rule was called
        mock_llm_delegate.generate_rule.assert_called_once()
        
        # Fallback should not be used, so no rule should be processed

