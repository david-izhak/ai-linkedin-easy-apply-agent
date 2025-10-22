"""
Literal strategy implementation.
"""

from typing import Any
from .base import BaseStrategy


class LiteralStrategy(BaseStrategy):
    """Strategy: Return a hardcoded literal value."""

    def __init__(self, params: dict, **kwargs):
        super().__init__(params)

    def get_value(self, profile: Any, a_field: dict) -> str | None:
        """Return the literal value from params."""
        return self.params.get("value", "")



