"""
NumericFromProfile strategy implementation.
"""

from .base import BaseStrategy
from ..profile_schema import CandidateProfile


class NumericFromProfileStrategy(BaseStrategy):
    """Strategy: Get numeric value from profile."""

    def __init__(self, params: dict, **kwargs):
        super().__init__(params)

    def get_value(self, profile: CandidateProfile, a_field: dict) -> str | None:
        """Get numeric value from profile and return as string."""
        key_path = self.params.get("key")
        if not key_path:
            return "0"

        value = profile.get_nested_value(key_path)
        if value is None:
            return "0"

        try:
            return str(int(value))
        except (ValueError, TypeError):
            return "0"



