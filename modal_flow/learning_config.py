"""
LearningConfig: Configuration for automatic rule learning mechanism.

This module provides configuration options for the self-learning system
that automatically generates rules from LLM decisions.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class LearningConfig:
    """
    Configuration for automatic rule learning mechanism.
    
    This configuration controls how the system learns from LLM decisions
    and automatically creates new rules for future use.
    
    Attributes:
        enabled: Master switch for learning mechanism
        auto_learn: Automatically add validated rules to RuleStore
        use_separate_rule_generation: Use separate LLM call for rule generation (recommended)
        rule_generation_fallback: Use suggest_rule from decision as fallback if separate generation fails
        confidence_threshold: Minimum confidence score (0.0-1.0) to accept LLM suggestions
        enable_duplicate_check: Check for duplicate rules before adding
        enable_pattern_validation: Validate regex patterns before adding
        enable_strategy_validation: Validate strategy structure before adding
        review_mode: Save suggestions to review file instead of auto-adding
        review_path: Path to pending rules file for review mode
    
    Example:
        >>> # Default configuration (auto-learning enabled)
        >>> config = LearningConfig()
        
        >>> # Strict mode (high confidence threshold)
        >>> config = LearningConfig(confidence_threshold=0.95)
        
        >>> # Review mode (manual approval required)
        >>> config = LearningConfig(review_mode=True)
    """
    
    # Master switch
    enabled: bool = True
    
    # Auto-learning behavior
    auto_learn: bool = True
    
    # Rule generation settings
    use_separate_rule_generation: bool = True  # Use separate LLM call for rule generation
    rule_generation_fallback: bool = True  # Use suggest_rule from decision as fallback if separate generation fails
    
    # Quality thresholds
    confidence_threshold: float = 0.70
    
    # Validation settings
    enable_duplicate_check: bool = True
    enable_pattern_validation: bool = True
    enable_strategy_validation: bool = True
    
    # Review mode settings
    review_mode: bool = False
    review_path: Optional[str] = "config/pending_rules.yaml"
    
    def __post_init__(self):
        """Validate configuration values."""
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                f"confidence_threshold must be between 0.0 and 1.0, "
                f"got {self.confidence_threshold}"
            )
        
        if self.review_mode and not self.review_path:
            raise ValueError("review_path must be set when review_mode is enabled")



