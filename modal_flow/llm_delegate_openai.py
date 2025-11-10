"""
OpenAI LLMDelegate implementation using existing LLMClient.

Based on creative phase design document.
"""

import logging
import asyncio
import json
import re
from typing import Optional, Dict, Any

from pydantic import HttpUrl

from llm.prompts import FIELD_DECISION_ENGINE_PROMPT, RULE_GENERATION_PROMPT
from modal_flow.llm_delegate import BaseLLMDelegate, LLMDecision, RuleSuggestion, StrategyDefinition
from modal_flow.profile_schema import CandidateProfile
from modal_flow.strategy_generator import StrategyGenerator


logger = logging.getLogger(__name__)


class OpenAILLMDelegate(BaseLLMDelegate):
    """
    OpenAI LLM delegate implementation.
    
    Uses the existing LLMClient from the project to make decisions.
    """
    
    def __init__(self, llm_client):
        """
        Initialize OpenAILLMDelegate.
        
        Args:
            llm_client: LLMClient instance from llm.llm_client
        """
        self.llm_client = llm_client
        self.system_prompt = FIELD_DECISION_ENGINE_PROMPT
        self.strategy_generator = StrategyGenerator()
    
    async def decide(
        self,
        field_info: Dict[str, Any],
        profile: CandidateProfile,
        job_context: Optional[Dict[str, Any]] = None
    ) -> LLMDecision:
        """
        Make a decision using LLM.
        
        Args:
            field_info: Field information dictionary
            profile: Candidate profile
            job_context: Optional job context
            
        Returns:
            LLMDecision with decision and value
        """
        try:
            # Build user prompt
            user_prompt = self._build_user_prompt(field_info, profile, job_context)
            
            logger.debug(f"LLM decision request for field: {field_info.get('question', 'unknown')}")
            
            # Use generate_structured_response from LLMClient
            # This handles structured output via function calling
            response = await asyncio.to_thread(
                self.llm_client.generate_structured_response,
                user_prompt,
                LLMDecision,
                self.system_prompt
            )
            
            # Response should already be LLMDecision instance
            if isinstance(response, LLMDecision):
                decision = response
            else:
                # Fallback: try to parse
                decision = LLMDecision.model_validate(response)
            
            logger.info(
                f"LLM decision: {decision.decision}={decision.value} "
                f"(confidence={decision.confidence:.2f})"
            )
            
            return decision
            
        except Exception as e:
            logger.error(f"LLM decision failed: {e}", exc_info=True)
            # Return a safe fallback decision
            return LLMDecision(
                decision="skip",
                value=None,
                confidence=0.0,
                suggest_rule=None
            )
    
    def _build_user_prompt(
        self,
        field_info: Dict[str, Any],
        profile: CandidateProfile,
        job_context: Optional[Dict[str, Any]]
    ) -> str:
        """
        Build user prompt for LLM.
        
        Args:
            field_info: Field information
            profile: Candidate profile
            job_context: Optional job context
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        
        # Field context
        prompt_parts.append("FIELD CONTEXT:")
        prompt_parts.append(f"  Question: {field_info.get('question', 'N/A')}")
        prompt_parts.append(f"  Type: {field_info.get('field_type', 'unknown')}")
        
        if field_info.get('options'):
            prompt_parts.append(f"  Available Options: {', '.join(field_info['options'])}")
        
        if field_info.get('required'):
            prompt_parts.append("  Required: Yes")
        
        # Constraints
        constraints = []
        if 'min' in field_info:
            constraints.append(f"min={field_info['min']}")
        if 'max' in field_info:
            constraints.append(f"max={field_info['max']}")
        if 'maxlength' in field_info:
            constraints.append(f"maxlength={field_info['maxlength']}")
        if 'pattern' in field_info:
            constraints.append(f"pattern={field_info['pattern']}")
        
        if constraints:
            prompt_parts.append(f"  Constraints: {', '.join(constraints)}")
        
        prompt_parts.append("")
        
        # Candidate profile (summary to avoid token bloat)
        prompt_parts.append("CANDIDATE PROFILE:")
        profile_summary = profile.to_json_summary()
        prompt_parts.append(f"  {self._format_dict(profile_summary, indent=2)}")
        
        prompt_parts.append("")
        
        # Job context (if available)
        if job_context:
            prompt_parts.append("JOB CONTEXT:")
            prompt_parts.append(f"  {self._format_dict(job_context, indent=2)}")
            prompt_parts.append("")
        
        # Instruction
        prompt_parts.append("INSTRUCTION:")
        prompt_parts.append("Make a decision for this field based on the candidate profile.")
        prompt_parts.append("If you cannot make a confident decision (confidence < 0.8), choose 'skip'.")
        
        return "\n".join(prompt_parts)
    
    async def generate_rule(
        self,
        field_info: Dict[str, Any],
        selected_value: Any,
        profile: CandidateProfile,
        job_context: Optional[Dict[str, Any]] = None
    ) -> Optional[RuleSuggestion]:
        """
        Generate a rule using LLM.
        
        Args:
            field_info: Field information dictionary
            selected_value: The value that was selected
            profile: Candidate profile
            job_context: Optional job context
            
        Returns:
            RuleSuggestion if successful, None otherwise
        """
        try:
            # Build user prompt for rule generation
            user_prompt = self._build_rule_generation_prompt(
                field_info, selected_value, profile, job_context
            )
            
            logger.debug(f"Generating rule for field: {field_info.get('question', 'unknown')}")
            
            # Use generate_structured_response for rule generation
            response = await asyncio.to_thread(
                self.llm_client.generate_structured_response,
                user_prompt,
                RuleSuggestion,
                RULE_GENERATION_PROMPT  # system prompt
            )
            
            # Handle response - may be dict or RuleSuggestion
            rule = None
            validation_error = None
            
            # NEW: Check and fix empty params BEFORE Pydantic validation
            if isinstance(response, dict):
                strategy_dict = response.get("strategy", {})
                if isinstance(strategy_dict, dict):
                    strategy_kind = strategy_dict.get("kind")
                    params = strategy_dict.get("params", {})
                    
                    # Check if strategy is completely empty
                    if strategy_dict == {} or not strategy_kind:
                        logger.warning("LLM returned rule with empty strategy, generating client-side")
                        client_strategy = self.strategy_generator.generate_strategy(
                            field_info=field_info,
                            selected_value=selected_value,
                            profile=profile,
                            question=field_info.get("question")
                        )
                        
                        if client_strategy:
                            # Replace empty strategy with client-generated one
                            response["strategy"] = {
                                "kind": client_strategy.kind,
                                "params": client_strategy.params
                            }
                            logger.info(f"Client-side strategy generated: {client_strategy.kind}")
                        else:
                            logger.warning("Could not generate client-side strategy, rule may be invalid")
                            return None
                    # Check if params are empty for strategies that require them
                    elif strategy_kind in ["one_of_options_from_profile", "numeric_from_profile", "profile_key"]:
                        if not params or not params.get("key"):
                            logger.warning(f"LLM returned {strategy_kind} with empty/missing 'key' param, generating client-side params")
                            
                            # Try to generate params client-side BEFORE validation
                            client_strategy = self.strategy_generator.generate_strategy(
                                field_info=field_info,
                                selected_value=selected_value,
                                profile=profile,
                                question=field_info.get("question")
                            )
                            
                            if client_strategy and client_strategy.kind == strategy_kind:
                                # Fill params from client-side generation
                                response["strategy"]["params"] = client_strategy.params
                                logger.info(f"Client-side params generated for {strategy_kind}: {client_strategy.params}")
                            elif client_strategy:
                                # If client strategy differs, replace completely
                                response["strategy"] = {
                                    "kind": client_strategy.kind,
                                    "params": client_strategy.params
                                }
                                logger.info(f"Client-side strategy replaced: {client_strategy.kind}")
                    # Check for one_of_options with empty params
                    elif strategy_kind == "one_of_options":
                        if not params or ("preferred" not in params and "synonyms" not in params):
                            logger.warning(f"LLM returned {strategy_kind} with empty/missing params, generating client-side params")
                            
                            client_strategy = self.strategy_generator.generate_strategy(
                                field_info=field_info,
                                selected_value=selected_value,
                                profile=profile,
                                question=field_info.get("question")
                            )
                            
                            if client_strategy:
                                response["strategy"] = {
                                    "kind": client_strategy.kind,
                                    "params": client_strategy.params
                                }
                                logger.info(f"Client-side strategy generated: {client_strategy.kind}")
            
            try:
                if isinstance(response, RuleSuggestion):
                    rule = response
                elif isinstance(response, dict):
                    rule = RuleSuggestion.model_validate(response)
                else:
                    rule = RuleSuggestion.model_validate(response)
            except Exception as e:
                # Pydantic validation failed - try to fix with client-side generation
                validation_error = e
                logger.warning(f"Rule validation failed: {e}, attempting to fix with client-side generation")
                
                # Try to extract strategy kind from error or response
                strategy_kind = None
                if isinstance(response, dict):
                    strategy_kind = response.get("strategy", {}).get("kind")
                
                # Try to generate client-side strategy
                client_strategy = self.strategy_generator.generate_strategy(
                    field_info=field_info,
                    selected_value=selected_value,
                    profile=profile,
                    question=field_info.get("question")
                )
                
                if client_strategy:
                    if strategy_kind and client_strategy.kind == strategy_kind:
                        # Try to fix params only
                        if isinstance(response, dict):
                            response["strategy"]["params"] = client_strategy.params
                            try:
                                rule = RuleSuggestion.model_validate(response)
                                logger.info(f"Fixed rule params for {strategy_kind}")
                            except Exception:
                                # If fixing params didn't work, replace strategy completely
                                response["strategy"] = {
                                    "kind": client_strategy.kind,
                                    "params": client_strategy.params
                                }
                                rule = RuleSuggestion.model_validate(response)
                                logger.info(f"Replaced strategy with client-side: {client_strategy.kind}")
                    else:
                        # Replace strategy completely
                        if isinstance(response, dict):
                            response["strategy"] = {
                                "kind": client_strategy.kind,
                                "params": client_strategy.params
                            }
                            try:
                                rule = RuleSuggestion.model_validate(response)
                                logger.info(f"Replaced strategy with client-side: {client_strategy.kind}")
                            except Exception:
                                # Create new rule with client strategy
                                question = field_info.get("question", "")
                                words = re.findall(r'\b\w+\b', question.lower())
                                key_words = [w for w in words if len(w) > 3][:5]
                                pattern = "(" + "|".join(key_words) + ")" if key_words else ".*"
                                
                                rule = RuleSuggestion(
                                    q_pattern=pattern,
                                    strategy=client_strategy,
                                    confidence=0.7
                                )
                                logger.info(f"Created new rule with client-side strategy: {client_strategy.kind}")
                else:
                    logger.warning("Could not generate client-side strategy to fix validation error")
                    rule = None
            
            # If validation failed or strategy is invalid, try to generate client-side
            if rule is None or not rule.strategy or not rule.strategy.kind:
                logger.warning("LLM returned rule without valid strategy, generating client-side")
                client_strategy = self.strategy_generator.generate_strategy(
                    field_info=field_info,
                    selected_value=selected_value,
                    profile=profile,
                    question=field_info.get("question")
                )
                
                if client_strategy:
                    if rule is None:
                        # Create new rule with client-generated strategy
                        question = field_info.get("question", "")
                        words = re.findall(r'\b\w+\b', question.lower())
                        key_words = [w for w in words if len(w) > 3][:5]
                        pattern = "(" + "|".join(key_words) + ")" if key_words else ".*"
                        
                        rule = RuleSuggestion(
                            q_pattern=pattern,
                            strategy=client_strategy,
                            confidence=0.7
                        )
                    else:
                        rule.strategy = client_strategy
                    logger.info(f"Client-side strategy generated: {client_strategy.kind}")
                else:
                    logger.warning("Could not generate client-side strategy, rule may be invalid")
                    return None
            
            # Check if params are empty for strategies that require them
            if rule and rule.strategy and rule.strategy.kind:
                strategies_requiring_params = [
                    "one_of_options",
                    "one_of_options_from_profile",
                    "numeric_from_profile",
                    "profile_key"
                ]
                
                if rule.strategy.kind in strategies_requiring_params:
                    params = rule.strategy.params or {}
                    is_empty = len(params) == 0
                    
                    # For one_of_options, check if preferred or synonyms is missing
                    if rule.strategy.kind == "one_of_options":
                        is_empty = "preferred" not in params and "synonyms" not in params
                    
                    # For strategies requiring key, check if key is missing
                    elif rule.strategy.kind in ["one_of_options_from_profile", "numeric_from_profile", "profile_key"]:
                        is_empty = "key" not in params or not params.get("key")
                    
                    if is_empty:
                        logger.warning(f"LLM returned {rule.strategy.kind} with empty/missing params, generating client-side params")
                        
                        # Try to generate params client-side
                        client_strategy = self.strategy_generator.generate_strategy(
                            field_info=field_info,
                            selected_value=selected_value,
                            profile=profile,
                            question=field_info.get("question")
                        )
                        
                        if client_strategy and client_strategy.kind == rule.strategy.kind:
                            # Fill params from client-side generation
                            rule.strategy.params = client_strategy.params
                            logger.info(f"Client-side params generated for {rule.strategy.kind}: {client_strategy.params}")
                        elif client_strategy:
                            # If client strategy differs, replace completely
                            rule.strategy = client_strategy
                            logger.info(f"Client-side strategy replaced: {client_strategy.kind}")
                        else:
                            logger.warning(f"Could not generate client-side params for {rule.strategy.kind}, rule will be rejected")
                            # Rule will be rejected by validation in rules_engine
                            return None
            
            logger.info(
                f"Rule generated: pattern='{rule.q_pattern}', "
                f"strategy={rule.strategy.kind}, confidence={rule.confidence:.2f}"
            )
            
            return rule
            
        except Exception as e:
            logger.error(f"Rule generation failed: {e}", exc_info=True)
            # Try to generate rule with client-side strategy as fallback
            try:
                logger.info("Attempting client-side rule generation as fallback")
                client_strategy = self.strategy_generator.generate_strategy(
                    field_info=field_info,
                    selected_value=selected_value,
                    profile=profile,
                    question=field_info.get("question")
                )
                
                if client_strategy:
                    # Generate a simple pattern from question
                    question = field_info.get("question", "")
                    # Simple pattern: extract key words
                    words = re.findall(r'\b\w+\b', question.lower())
                    # Take first 3-5 meaningful words
                    key_words = [w for w in words if len(w) > 3][:5]
                    pattern = "(" + "|".join(key_words) + ")" if key_words else ".*"
                    
                    rule = RuleSuggestion(
                        q_pattern=pattern,
                        strategy=client_strategy,
                        confidence=0.7  # Lower confidence for client-generated rules
                    )
                    logger.info(f"Client-side rule generated: pattern='{pattern}', strategy={client_strategy.kind}")
                    return rule
            except Exception as fallback_error:
                logger.error(f"Client-side rule generation also failed: {fallback_error}", exc_info=True)
            
            return None
    
    def _build_rule_generation_prompt(
        self,
        field_info: Dict[str, Any],
        selected_value: Any,
        profile: CandidateProfile,
        job_context: Optional[Dict[str, Any]]
    ) -> str:
        """
        Build user prompt for rule generation.
        
        Args:
            field_info: Field information
            selected_value: The value that was selected
            profile: Candidate profile
            job_context: Optional job context
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = []
        
        # Field context
        prompt_parts.append("FIELD CONTEXT:")
        prompt_parts.append(f"  Question: {field_info.get('question', 'N/A')}")
        prompt_parts.append(f"  Type: {field_info.get('field_type', 'unknown')}")
        
        if field_info.get('options'):
            prompt_parts.append(f"  Available Options: {', '.join(field_info['options'])}")
        
        prompt_parts.append(f"  Selected Value: {selected_value}")
        
        # Constraints
        constraints = []
        if 'min' in field_info:
            constraints.append(f"min={field_info['min']}")
        if 'max' in field_info:
            constraints.append(f"max={field_info['max']}")
        if 'maxlength' in field_info:
            constraints.append(f"maxlength={field_info['maxlength']}")
        if 'pattern' in field_info:
            constraints.append(f"pattern={field_info['pattern']}")
        
        if constraints:
            prompt_parts.append(f"  Constraints: {', '.join(constraints)}")
        
        prompt_parts.append("")
        
        # Candidate profile (summary)
        prompt_parts.append("CANDIDATE PROFILE:")
        profile_summary = profile.to_json_summary()
        prompt_parts.append(f"  {self._format_dict(profile_summary, indent=2)}")
        
        prompt_parts.append("")
        
        # Job context (if available)
        if job_context:
            prompt_parts.append("JOB CONTEXT:")
            prompt_parts.append(f"  {self._format_dict(job_context, indent=2)}")
            prompt_parts.append("")
        
        # Instruction
        prompt_parts.append("INSTRUCTION:")
        prompt_parts.append("Generate a reusable rule that can match this field type and fill it with the selected value.")
        prompt_parts.append("The rule should work for similar questions in the future.")
        
        return "\n".join(prompt_parts)
    
    def _format_dict(self, d: Dict[str, Any], indent: int = 0) -> str:
        """Format dictionary for prompt (simple version)."""
        
        def json_converter(o: Any) -> str:
            """Convert non-serializable objects to strings."""
            if isinstance(o, HttpUrl):
                return str(o)
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

        return json.dumps(d, indent=indent, ensure_ascii=False, default=json_converter)

