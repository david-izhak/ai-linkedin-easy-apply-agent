"""
OneOfOptions strategy implementation.
"""

from typing import Any
from ..normalizer import QuestionNormalizer
from ..profile_schema import CandidateProfile
from .base import BaseStrategy


class OneOfOptionsStrategy(BaseStrategy):
    """Strategy: Select one option from a list based on synonyms."""

    def __init__(self, params: dict, normalizer: QuestionNormalizer, logger=None):
        super().__init__(params)
        self.normalizer = normalizer
        self.logger = logger

    def get_value(self, profile: Any, a_field: dict) -> str | None:
        """Select best matching option using synonyms and fuzzy matching."""
        options = a_field.get("options")
        if not options:
            return None

        synonyms = self.params.get("synonyms", {})
        preferred = self.params.get("preferred", [])

        # If preferred list is provided, try to match preferred options first
        if preferred:
            for preferred_val in preferred:
                preferred_norm = self.normalizer.normalize_string(preferred_val).lower()
                for option in options:
                    option_norm = self.normalizer.normalize_string(option).lower()
                    if option_norm == preferred_norm:
                        return option
                    # Check if preferred is contained in option
                    if preferred_norm in option_norm or option_norm in preferred_norm:
                        if len(preferred_norm) >= 2:  # Avoid very short false matches
                            return option
                
                # Try fuzzy match for preferred values
                if hasattr(self.normalizer, 'find_best_match'):
                    best_match = self.normalizer.find_best_match(preferred_val, options)
                    if best_match:
                        return best_match

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
        if synonyms and hasattr(self.normalizer, 'find_best_match'):
            for canonical, syns in synonyms.items():
                best_match = self.normalizer.find_best_match(canonical, options)
                if best_match:
                    return best_match

        # IMPORTANT: Don't return first option as fallback if we have synonyms/preferred
        # Return None instead to signal that rule failed and LLM should be used
        if synonyms or preferred:
            if self.logger:
                self.logger.warning(
                    f"OneOfOptionsStrategy: Could not match any option. "
                    f"options={options}, synonyms={synonyms}, preferred={preferred}"
                )
            return None
        
        # Only return first option if no synonyms/preferred specified (backward compatibility)
        # This maintains backward compatibility for rules that don't specify synonyms
        return options[0] if options else None


class OneOfOptionsFromProfileStrategy(BaseStrategy):
    """
    Strategy to select an option based on a value from the profile,
    which is then matched against a set of synonyms.
    """

    def __init__(self, params: dict, normalizer: QuestionNormalizer, logger=None):
        super().__init__(params)
        self.normalizer = normalizer

    def get_value(self, profile: CandidateProfile, a_field: dict) -> str | None:
        options = a_field.get("options")
        if not options:
            return None

        profile_key = self.params.get("key")
        if not profile_key:
            return None

        # Исправить: использовать get_nested_value вместо get
        profile_value = profile.get_nested_value(profile_key)
        if profile_value is None:
            return None

        synonyms_map = self.params.get("synonyms", {})
        if not synonyms_map:
            # Если нет synonyms, пытаемся использовать значение напрямую
            profile_str = str(profile_value).lower()
            for option in options:
                if self.normalizer.normalize_text(option).lower() == profile_str:
                    return option
            return None

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



