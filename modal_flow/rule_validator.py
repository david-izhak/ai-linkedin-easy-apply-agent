"""
RuleSuggestionValidator: Validates LLM-suggested rules before adding to RuleStore.

This module ensures that only high-quality, valid rules are automatically
added to the system.
"""

import re
import logging
from typing import Dict, Any, Tuple, List, Optional


class RuleSuggestionValidator:
    """
    Validator for LLM-suggested rules.
    
    Validates rule suggestions from LLM before they are added to the RuleStore.
    Checks pattern validity, strategy structure, and other quality criteria.
    
    Attributes:
        available_strategies: List of valid strategy kinds
        logger: Logger instance for validation events
    
    Example:
        >>> validator = RuleSuggestionValidator(["literal", "profile_key"])
        >>> is_valid, error = validator.validate(suggest_rule)
        >>> if not is_valid:
        ...     print(f"Validation failed: {error}")
    """
    
    def __init__(
        self,
        available_strategies: List[str],
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize RuleSuggestionValidator.
        
        Args:
            available_strategies: List of valid strategy kinds (e.g., ["literal", "profile_key"])
            logger: Optional logger instance
        """
        self.available_strategies = available_strategies
        self.logger = logger or logging.getLogger(__name__)
    
    def validate(self, suggest_rule: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a rule suggestion from LLM.
        
        Performs comprehensive validation including:
        - Structure validation (presence of required fields)
        - Pattern validation (regex syntax and quality)
        - Strategy validation (known strategy kind and valid params)
        
        Args:
            suggest_rule: Dictionary containing q_pattern and strategy
                Expected structure:
                {
                    "q_pattern": "<regex pattern>",
                    "strategy": {
                        "kind": "<strategy_name>",
                        "params": {...}
                    }
                }
        
        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if validation passed, False otherwise
            - error_message: Empty string if valid, error description if invalid
        
        Example:
            >>> suggest_rule = {
            ...     "q_pattern": "(python|питон)",
            ...     "strategy": {"kind": "literal", "params": {"value": True}}
            ... }
            >>> is_valid, error = validator.validate(suggest_rule)
            >>> assert is_valid == True
        """
        # Check if suggest_rule exists
        if not suggest_rule:
            return False, "Empty suggest_rule"
        
        # Validate q_pattern
        is_valid, error_msg = self._validate_pattern(suggest_rule)
        if not is_valid:
            return False, error_msg
        
        # Validate strategy
        is_valid, error_msg = self._validate_strategy(suggest_rule)
        if not is_valid:
            return False, error_msg
        
        return True, ""
    
    def _validate_pattern(self, suggest_rule: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate q_pattern field.
        
        Args:
            suggest_rule: Rule suggestion dictionary
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        q_pattern = suggest_rule.get("q_pattern", "").strip()
        
        # Check presence
        if not q_pattern:
            return False, "Missing or empty q_pattern"
        
        # Check minimum length (quality heuristic)
        if len(q_pattern) < 3:
            self.logger.debug(f"Pattern too short: '{q_pattern}'")
            return False, "Pattern too short (minimum 3 characters)"
        
        # Check maximum length (prevent unreasonably long patterns)
        if len(q_pattern) > 200:
            self.logger.debug(f"Pattern too long: {len(q_pattern)} characters")
            return False, "Pattern too long (maximum 200 characters)"
        
        # Validate regex syntax
        try:
            re.compile(q_pattern)
        except re.error as e:
            self.logger.debug(f"Invalid regex: '{q_pattern}', error: {e}")
            return False, f"Invalid regex pattern: {e}"
        
        # Check for dangerous patterns (optional, can be extended)
        dangerous_patterns = [
            r'\.\*\.\*',  # Greedy double wildcard
            r'\.\+\.\+',  # Greedy double plus
        ]
        
        for dangerous in dangerous_patterns:
            if re.search(dangerous, q_pattern):
                self.logger.warning(
                    f"Potentially dangerous pattern detected: '{q_pattern}'"
                )
                # For now, just warn, don't reject
                # return False, "Pattern contains dangerous constructs"
        
        return True, ""
    
    def _validate_strategy(self, suggest_rule: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate strategy field.
        
        Args:
            suggest_rule: Rule suggestion dictionary
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        strategy = suggest_rule.get("strategy")
        
        # Check presence and type
        if not strategy or not isinstance(strategy, dict):
            return False, "Missing or invalid strategy (must be a dictionary)"
        
        # Check strategy kind
        strategy_kind = strategy.get("kind")
        if not strategy_kind:
            return False, "Missing strategy.kind"
        
        if not isinstance(strategy_kind, str):
            return False, "strategy.kind must be a string"
        
        # Check if strategy kind is known
        if strategy_kind not in self.available_strategies:
            return False, f"Unknown strategy kind: '{strategy_kind}'"
        
        # Check params structure (if present)
        params = strategy.get("params")
        if params is not None and not isinstance(params, dict):
            return False, "strategy.params must be a dictionary"
        
        # Validate that required params are present for each strategy kind
        if strategy_kind == "literal":
            if not params or "value" not in params:
                return False, "Strategy 'literal' requires 'value' in params"
        
        elif strategy_kind == "profile_key":
            if not params or "key" not in params or not params.get("key"):
                return False, "Strategy 'profile_key' requires 'key' in params"
        
        elif strategy_kind == "numeric_from_profile":
            if not params or "key" not in params or not params.get("key"):
                return False, "Strategy 'numeric_from_profile' requires 'key' in params"
        
        elif strategy_kind == "one_of_options":
            if not params or ("preferred" not in params and "synonyms" not in params):
                return False, "Strategy 'one_of_options' requires either 'preferred' or 'synonyms' in params"
        
        elif strategy_kind == "one_of_options_from_profile":
            if not params or "key" not in params or not params.get("key"):
                return False, "Strategy 'one_of_options_from_profile' requires 'key' in params"
            # synonyms is optional but recommended
        
        elif strategy_kind == "salary_by_currency":
            if not params or "base_key_template" not in params or "default_currency" not in params:
                return False, "Strategy 'salary_by_currency' requires 'base_key_template' and 'default_currency' in params"
        
        return True, ""
    
    def validate_batch(
        self, 
        suggestions: List[Dict[str, Any]]
    ) -> List[Tuple[bool, str]]:
        """
        Validate multiple rule suggestions.
        
        Args:
            suggestions: List of rule suggestion dictionaries
        
        Returns:
            List of (is_valid, error_message) tuples
        
        Example:
            >>> results = validator.validate_batch([rule1, rule2, rule3])
            >>> valid_rules = [s for s, (v, _) in zip(suggestions, results) if v]
        """
        return [self.validate(suggestion) for suggestion in suggestions]



