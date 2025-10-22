"""
OneOfOptions strategy implementation.
"""

from typing import Any
from ..normalizer import QuestionNormalizer
from .base import BaseStrategy


class OneOfOptionsStrategy(BaseStrategy):
    """Strategy: Select one option from a list based on synonyms."""

    def __init__(self, params: dict, normalizer: QuestionNormalizer, logger=None):
        super().__init__(params)
        self.normalizer = normalizer

    def get_value(self, profile: Any, a_field: dict) -> str | None:
        """Select best matching option using synonyms and fuzzy matching."""
        options = a_field.get("options")
        if not options:
            return None

        synonyms = self.params.get("synonyms", {})

        # Try to match each option against canonical forms and synonyms
        for option in options:
            option_norm = self.normalizer.normalize_text(option)

            # Check if option matches any canonical form
            for canonical, syns in synonyms.items():
                canonical_norm = self.normalizer.normalize_text(canonical)
                if option_norm == canonical_norm:
                    return option

                # Check synonyms
                for syn in syns:
                    syn_norm = self.normalizer.normalize_text(syn)
                    if option_norm == syn_norm:
                        return option

        # If no exact match, try fuzzy matching
        # Prefer options that match canonical forms
        for canonical, syns in synonyms.items():
            best_match = self.normalizer.find_best_match(canonical, options)
            if best_match:
                return best_match

        # Return first option as fallback
        return options[0] if options else None


class OneOfOptionsFromProfileStrategy(BaseStrategy):
    """
    Strategy to select an option based on a value from the profile,
    which is then matched against a set of synonyms.
    """

    def __init__(self, params: dict, normalizer: QuestionNormalizer, logger=None):
        super().__init__(params)
        self.normalizer = normalizer

    def get_value(self, profile: dict, a_field: dict) -> str | None:
        options = a_field.get("options")
        if not options:
            return None

        profile_key = self.params.get("key")
        profile_value = profile.get(profile_key)
        if profile_value is None:
            return None

        synonyms_map = self.params.get("synonyms", {})
        target_synonyms = []
        for key, value in synonyms_map.items():
            if key.lower() == str(profile_value).lower():
                target_synonyms = value
                break
        
        if not target_synonyms:
            return None

        for option in options:
            for synonym in target_synonyms:
                if self.normalizer.normalize_text(option) == self.normalizer.normalize_text(synonym):
                    return option
        
        return None



