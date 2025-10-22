"""
Base strategy interface for rule execution.

Based on creative phase design document (Strategy Pattern).
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Dict

from modal_flow.profile_schema import CandidateProfile


class IStrategy(ABC):
    """Abstract base class for rule strategies."""
    
    @abstractmethod
    def execute(
        self,
        profile: CandidateProfile,
        options: Optional[List[str]],
        params: Dict[str, Any],
        normalizer: Any  # QuestionNormalizer
    ) -> Any:
        """
        Execute the rule strategy and return a decision value.
        
        Args:
            profile: Candidate profile
            options: Available options (for select/radio fields)
            params: Strategy-specific parameters
            normalizer: QuestionNormalizer instance
            
        Returns:
            Decision value (string, int, bool, etc.)
        """
        pass


class BaseStrategy(IStrategy, ABC):
    def __init__(self, params: dict):
        self.params = params

    def execute(
        self,
        profile: CandidateProfile,
        options: Optional[List[str]],
        params: Dict[str, Any],
        normalizer: Any  # QuestionNormalizer
    ) -> Any:
        a_field = {"options": options}
        # For simplicity, passing the normalizer via kwargs if needed,
        # but child classes can get it from the factory.
        return self.get_value(profile, a_field)

    @abstractmethod
    def get_value(self, profile: dict, a_field: dict) -> str | None:
        """
        Retrieves the value for a field based on the strategy.
        :param profile: The user's profile data.
        :param a_field: The field dictionary.
        :return: The value as a string, or None.
        """
        pass



