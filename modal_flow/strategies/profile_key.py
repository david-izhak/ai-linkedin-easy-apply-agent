"""
ProfileKey strategy implementation.
"""

from typing import Any
from ..profile_schema import CandidateProfile
from .base import BaseStrategy


class ProfileKeyStrategy(BaseStrategy):
    """Strategy: Get value from candidate profile using a key path."""

    def __init__(self, params: dict, **kwargs):
        super().__init__(params)

    def get_value(self, profile: CandidateProfile, a_field: dict) -> str | None:
        """Get value from profile using dot notation key path."""
        key_path = self.params.get("key")
        if not key_path:
            return None

        value = profile.get_nested_value(key_path)
        return str(value) if value is not None else None



