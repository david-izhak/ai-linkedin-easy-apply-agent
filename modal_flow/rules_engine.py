"""
RulesEngine: Core decision-making engine for form field filling.

Based on creative phase design document.
"""

import logging
import re
from typing import Optional, Dict, Any, List

from modal_flow.profile_schema import CandidateProfile
from modal_flow.rules_store import RuleStore
from modal_flow.field_signature import FieldSignature, options_fingerprint
from modal_flow.normalizer import QuestionNormalizer
from modal_flow.learning_config import LearningConfig
from modal_flow.rule_validator import RuleSuggestionValidator
from modal_flow.strategies import create_strategy, STRATEGY_MAPPING


class RulesEngine:
    """
    Rules-first decision engine for form field filling.
    
    Prioritizes rules from RuleStore, falls back to heuristics,
    and delegates to LLM as last resort.
    """
    
    def __init__(
        self,
        profile: CandidateProfile,
        rule_store: RuleStore,
        normalizer: Optional[QuestionNormalizer] = None,
        llm_delegate: Optional[Any] = None,  # BaseLLMDelegate
        learning_config: Optional[LearningConfig] = None,
        logger: Optional[logging.Logger] = None
        ,
        # Control whether the simple text-field -> bio heuristic is used.
        # Default: disabled to prefer LLM decisions unless explicitly enabled.
        text_field_bio_heuristic_enabled: bool = False
    ):
        """
        Initialize RulesEngine.
        
        Args:
            profile: Candidate profile
            rule_store: RuleStore instance
            normalizer: QuestionNormalizer instance
            llm_delegate: Optional LLMDelegate for fallback
            learning_config: Optional configuration for automatic learning
            logger: Optional logger instance
        """
        self.profile = profile
        self.rule_store = rule_store
        self.normalizer = normalizer or QuestionNormalizer()
        self.llm_delegate = llm_delegate
        self.learning_config = learning_config or LearningConfig()
        self.logger = logger or logging.getLogger(__name__)
        # New: flag to enable/disable the fallback that fills any text field
        # with profile.short_bio_en/ru. Default is False (disabled).
        self.text_field_bio_heuristic_enabled = text_field_bio_heuristic_enabled

        # Initialize rule validator for learning mechanism.
        # The strategy instances are now created on-the-fly by the factory,
        # so we just need the keys from the mapping.
        self.rule_validator = RuleSuggestionValidator(
            available_strategies=list(STRATEGY_MAPPING.keys()),
            logger=self.logger
        )
    
    async def decide(
        self,
        question: str,
        field_type: str,
        options: Optional[List[str]] = None,
        site: str = "*",
        form_kind: str = "job_apply",
        locale: str = "en",
        constraints: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Make a decision for a form field.
        
        Decision flow:
        1. Find matching rule in RuleStore
        2. Execute rule strategy
        3. Fall back to heuristics if no rule found
        4. Delegate to LLM if heuristics fail
        
        Args:
            question: Field question text
            field_type: Type of field (radio, checkbox, etc.)
            options: Available options (for select/radio fields)
            site: Site context (default: "*")
            form_kind: Form kind (default: "job_apply")
            locale: Locale (default: "en")
            
        Returns:
            Decision value (string, int, bool, etc.)
        """
        # Normalize question
        q_norm = self.normalizer.normalize_text(question)
        
        # Log normalization for debugging
        self.logger.debug(f"Question normalized: '{question}' -> '{q_norm}'")
        
        # Create field signature
        opts_fp = options_fingerprint(options) if options else None
        signature = FieldSignature(
            field_type=field_type,
            q_norm=q_norm,
            opts_fp=opts_fp,
            site=site,
            form_kind=form_kind,
            locale=locale
        )
        
        # Step 1: Find rule
        rule = self.rule_store.find(signature)
        if rule:
            self.logger.debug(f"Rule found: {rule.get('id')}")
            strategy_kind = rule.get("strategy", {}).get("kind")
            params = rule.get("strategy", {}).get("params", {})

            if strategy_kind:
                try:
                    self.logger.debug(f"Creating strategy: {strategy_kind} with params: {params}")

                    # If the rule provides a q_pattern, try to extract named groups
                    # and substitute them into strategy params. This enables rules like
                    # q_pattern: "(?P<skill>python|java)" with strategy.params.key
                    # set to "years_experience.{skill}" so the actual key is resolved
                    # at runtime.
                    rule_sig = rule.get("signature", {})
                    q_pattern = rule_sig.get("q_pattern", "")
                    if q_pattern:
                        try:
                            match = re.search(q_pattern, signature.q_norm, re.IGNORECASE)
                            if match:
                                # Only substitute string parameters that contain placeholders
                                params = params.copy() if isinstance(params, dict) else {}
                                for k, v in list(params.items()):
                                    if isinstance(v, str) and "{" in v and "}" in v:
                                        try:
                                            # Use match.groupdict() first for named groups
                                            gd = match.groupdict()
                                            if gd:
                                                params[k] = v.format(**gd)
                                            else:
                                                # Fallback to positional groups
                                                params[k] = v.format(*match.groups())
                                        except Exception:
                                            # If substitution fails, keep original param
                                            pass
                        except re.error:
                            # Invalid regex in rule - ignore substitutions
                            pass

                    strategy = create_strategy(
                        strategy_kind=strategy_kind,
                        params=params,
                        normalizer=self.normalizer,
                        logger=self.logger
                    )
                    self.logger.debug(f"Strategy created: {type(strategy).__name__}")
                    decision = strategy.get_value(
                        profile=self.profile,
                        a_field={"question": question, "options": options},
                    )
                    self.logger.info(f"Rule decision: {decision}")
                    return decision
                except Exception as e:
                    self.logger.error(f"Strategy execution failed: {e}", exc_info=True)
            else:
                self.logger.warning(f"Strategy kind not specified in rule: {rule.get('id')}")

        # Step 2: Heuristic fallback
        heuristic_decision = self._apply_heuristics(q_norm, field_type, options, question)
        if heuristic_decision is not None:
            self.logger.info(f"Heuristic decision: {heuristic_decision}")
            return heuristic_decision
        
        # Step 3: LLM Delegation
        if self.llm_delegate:
            # Log when delegating boolean-like groups to LLM so we can collect examples
            # for building rules and to measure frequency of LLM usage.
            if field_type in ("radio", "checkbox"):
                try:
                    # Prepare a compact profile summary for logging (avoid huge dumps)
                    profile_summary = self.profile.to_json_summary() if hasattr(self.profile, "to_json_summary") else {}
                except Exception:
                    profile_summary = {}

                # options may be None or a list; display safely
                opts_display = options if options is not None else []

                # WARNING: logs may contain personal profile data; ensure log access is restricted
                self.logger.info(
                    "[LLM_DELEGATE] No rule/heuristic found for boolean field; delegating to LLM. "
                    f"question='{question}', q_norm='{q_norm}', options={opts_display}, "
                    f"site='{site}', form_kind='{form_kind}', locale='{locale}', "
                    f"profile_summary={profile_summary}"
                )

            self.logger.info("Delegating to LLM")
            
            # Build field_info for LLM
            field_info = {
                "question": question,
                "field_type": field_type,
                "options": options,
                "required": True,  # Default to required
            }
            
            # Add constraints if provided
            if constraints:
                field_info.update(constraints)
            
            try:
                # Await the async call to the LLM delegate
                llm_decision = await self.llm_delegate.decide(field_info, self.profile)
                
                # Extract value from LLMDecision object
                if llm_decision and llm_decision.decision != "skip":
                    self.logger.info(f"LLM decision: {llm_decision.value} (confidence={llm_decision.confidence:.2f})")
                    
                    # ◄────────── НОВОЕ: Обработка предложенного правила ──────────►
                    if self.learning_config.enabled and self.learning_config.auto_learn:
                        # Создать signature для этого поля
                        opts_fp = options_fingerprint(options) if options else None
                        q_norm = self.normalizer.normalize_text(question)
                        signature = FieldSignature(
                            field_type=field_type,
                            q_norm=q_norm,
                            opts_fp=opts_fp,
                            site=site,
                            form_kind=form_kind,
                            locale=locale
                        )
                        
                        # Обработать предложенное правило
                        await self._process_suggested_rule(
                            llm_decision=llm_decision,
                            signature=signature
                        )
                    # ◄─────────────────────────────────────────────────────────────►
                    
                    return llm_decision.value
                else:
                    self.logger.info("LLM suggested to skip this field")
                    return None
            except Exception as e:
                self.logger.error(f"LLM delegate failed: {e}", exc_info=True)
                return None
        
        # No decision could be made
        self.logger.warning("No decision could be made")
        return None
    
    async def _process_suggested_rule(
        self,
        llm_decision: Any,  # LLMDecision
        signature: FieldSignature
    ) -> None:
        """
        Process and potentially save a rule suggested by LLM.
        
        This method implements the automatic learning mechanism:
        1. Validates the suggestion
        2. Checks confidence threshold
        3. Verifies no duplicates exist
        4. Saves the rule to RuleStore
        
        Args:
            llm_decision: LLMDecision object containing suggest_rule
            signature: Field signature for the rule
        
        Returns:
            None (side effect: may add rule to RuleStore)
        """
        suggest_rule = llm_decision.suggest_rule
        confidence = llm_decision.confidence
        
        # Check 1: Is there a suggestion?
        if not suggest_rule:
            self.logger.debug("No rule suggestion from LLM")
            return
        
        # Check 2: Is confidence sufficient?
        if confidence < self.learning_config.confidence_threshold:
            self.logger.warning(
                f"Rule suggestion rejected: confidence {confidence:.2f} "
                f"below threshold {self.learning_config.confidence_threshold}"
            )
            return
        
        # Check 3: Validate structure
        if self.learning_config.enable_pattern_validation:
            is_valid, error_msg = self.rule_validator.validate(suggest_rule)
            if not is_valid:
                self.logger.warning(f"Rule suggestion validation failed: {error_msg}")
                return
        
        # Check 4: Check for duplicates
        if self.learning_config.enable_duplicate_check:
            q_pattern = suggest_rule.get("q_pattern", "")
            if self.rule_store.is_duplicate_rule(signature, q_pattern):
                self.logger.info(f"Duplicate rule detected, skipping: {q_pattern}")
                return
        
        # All checks passed - add the rule
        try:
            new_rule = self.rule_store.add_llm_rule(
                signature=signature,
                suggest_rule=suggest_rule,
                confidence=confidence
            )
            
            self.logger.info(
                f"✅ New rule learned and saved: {new_rule['id']} "
                f"(pattern='{suggest_rule.get('q_pattern')}', confidence={confidence:.2f})"
            )
        except Exception as e:
            self.logger.error(f"Failed to add LLM rule: {e}", exc_info=True)
    
    def _apply_heuristics(
        self,
        q_norm: str,
        field_type: str,
        options: Optional[List[str]],
        question: str
    ) -> Optional[Any]:
        """
        Apply built-in heuristics for common questions.
        
        Args:
            q_norm: Normalized question text
            field_type: Field type
            options: Available options
            
        Returns:
            Heuristic decision or None
        """
        # Removed hard-coded years-of-experience heuristic.
        # This logic is now expected to be covered by a rule stored in RuleStore
        # which can use a q_pattern with a named capture group 'skill' and a
        # strategy 'numeric_from_profile' with params.key = "years_experience.{skill}".

        # Heuristic for skills checkboxes
        if field_type == "checkbox":
            skill_name_from_form = q_norm
            
            # New: Normalize the skill name to its canonical form
            canonical_skill = self.normalizer.map_skill_to_canonical(skill_name_from_form)
            
            # Get years_experience as a dictionary
            experience_dict = self.profile.years_experience.model_dump() if self.profile.years_experience else {}
            
            # Check if the canonical skill exists in the experience dict with a positive value
            if canonical_skill in experience_dict and experience_dict[canonical_skill] > 0:
                # Return True to check the box
                return True
        
        # Salary heuristic
        if re.search(r"(salary|compensation|зарплата)", q_norm, re.I):
            # Try to get salary from profile
            # Detect currency mentioned in the question using normalizer
            try:
                currency = self.normalizer.detect_currency(q_norm, raw_text=question)
            except Exception:
                currency = None

            # Default currency is NIS
            if not currency:
                currency = "nis"

            key = f"salary_expectation.monthly_net_{currency}"
            salary_value = self.profile.get_nested_value(key)
            if salary_value:
                return salary_value
        
        # Boolean/radio preference heuristic removed
        # Choosing a default "Yes" can lead to incorrect/unsafe answers for some forms.
        # Prefer delegating ambiguous boolean/radio decisions to the LLM so it can use
        # the candidate profile and question context to decide. If you need a
        # deterministic preference later, implement it as a RuleStore rule or
        # enable a configurable radio_preference in QuestionNormalizer.

        # Text field default
        if field_type == "text":
            # Only use the simple bio heuristic when explicitly enabled.
            if not getattr(self, "text_field_bio_heuristic_enabled", False):
                # Heuristic intentionally disabled: prefer LLM or rules.
                self.logger.debug("Text-field bio heuristic is disabled. Skipping.")
            else:
                bio = self.profile.short_bio_en or self.profile.short_bio_ru
                if bio:
                    return bio[:200]  # Truncate for safety

