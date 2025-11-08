"""
OpenAI LLMDelegate implementation using existing LLMClient.

Based on creative phase design document.
"""

import logging
import asyncio
import json
from typing import Optional, Dict, Any

from pydantic import HttpUrl

from llm.prompts import FIELD_DECISION_ENGINE_PROMPT
from modal_flow.llm_delegate import BaseLLMDelegate, LLMDecision
from modal_flow.profile_schema import CandidateProfile


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
        prompt_parts.append("If possible, suggest a rule pattern that could match this field in the future.")
        
        return "\n".join(prompt_parts)
    
    def _format_dict(self, d: Dict[str, Any], indent: int = 0) -> str:
        """Format dictionary for prompt (simple version)."""
        
        def json_converter(o: Any) -> str:
            """Convert non-serializable objects to strings."""
            if isinstance(o, HttpUrl):
                return str(o)
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

        return json.dumps(d, indent=indent, ensure_ascii=False, default=json_converter)

