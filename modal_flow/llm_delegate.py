"""
LLMDelegate: Abstraction layer for LLM-based form field decisions.

Based on creative phase design document.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Literal

from pydantic import BaseModel, Field

from modal_flow.profile_schema import CandidateProfile


class SuggestedStrategy(BaseModel):
    """Suggested strategy structure for new rules."""
    kind: str
    params: Optional[Dict[str, Any]] = None


class LLMDecision(BaseModel):
    """
    Structured response from LLM for field decision.
    
    Based on technical specification section 4.4.
    """
    decision: Literal["select", "text", "number", "check", "skip"]
    value: Any
    confidence: float = Field(..., ge=0, le=1)
    suggest_rule: Optional[Dict[str, Any]] = None
    
    class Config:
        # Allow extra fields for flexibility
        extra = "allow"


class BaseLLMDelegate(ABC):
    """
    Abstract base class for LLM delegates.
    
    Provides a common interface for different LLM providers.
    """
    
    @abstractmethod
    async def decide(
        self,
        field_info: Dict[str, Any],
        profile: CandidateProfile,
        job_context: Optional[Dict[str, Any]] = None
    ) -> LLMDecision:
        """
        Ask the LLM to make a decision for a given field.
        
        Args:
            field_info: Dictionary containing field information:
                - question: str
                - field_type: str (radio, checkbox, select, text, number)
                - options: Optional[List[str]]
                - required: bool
            profile: Candidate profile
            job_context: Optional job context (job title, description, etc.)
            
        Returns:
            LLMDecision with decision, value, confidence, and optional suggest_rule
        """
        pass

