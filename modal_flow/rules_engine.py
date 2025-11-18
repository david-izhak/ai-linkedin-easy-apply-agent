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
from modal_flow.llm_delegate import LLMDecision


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
        self.logger.info(
            f"[RULES_ENGINE] Looking for rule: field_type='{field_type}', "
            f"q_norm='{q_norm}', opts_fp='{signature.opts_fp}'"
        )
        rule = self.rule_store.find(signature)
        rule_found = rule is not None
        rule_failed = False
        failed_rule_id: Optional[str] = None
        failed_rule_reason: Optional[str] = None
        failed_rule_context: Dict[str, Any] = {}
        
        if rule:
            self.logger.info(
                f"[RULES_ENGINE] Rule found: id='{rule.get('id')}', "
                f"pattern='{rule.get('signature', {}).get('q_pattern')}', "
                f"strategy='{rule.get('strategy', {}).get('kind')}'"
            )
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
                                for k, v in params.items():
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
                    
                    # NEW: Validate decision - if rule found but returns None/invalid, treat as error
                    if decision is None:
                        rule_failed = True
                        failed_rule_id = rule.get("id")
                        failed_rule_reason = "strategy returned None"
                        failed_rule_context = {
                            "field_type": field_type,
                            "q_norm": q_norm,
                            "options": options,
                            "site": site,
                            "form_kind": form_kind,
                            "locale": locale,
                        }
                        self.logger.warning(
                            "[RULE_FAILURE] Rule '%s' matched but strategy returned None. "
                            "Manual review required. Context=%s",
                            failed_rule_id,
                            failed_rule_context,
                        )
                        # Fall through to LLM delegation
                    elif self._is_invalid_decision(decision, field_type, options):
                        rule_failed = True
                        failed_rule_id = rule.get("id")
                        failed_rule_reason = f"strategy returned invalid value '{decision}'"
                        failed_rule_context = {
                            "field_type": field_type,
                            "q_norm": q_norm,
                            "options": options,
                            "site": site,
                            "form_kind": form_kind,
                            "locale": locale,
                        }
                        self.logger.warning(
                            "[RULE_FAILURE] Rule '%s' matched but returned invalid value '%s'. "
                            "Manual review required. Context=%s",
                            failed_rule_id,
                            decision,
                            failed_rule_context,
                        )
                        # Fall through to LLM delegation
                    else:
                        # Decision is valid, return it
                        return decision
                except Exception as e:
                    rule_failed = True
                    failed_rule_id = rule.get("id")
                    failed_rule_reason = f"strategy raised exception: {e}"
                    failed_rule_context = {
                        "field_type": field_type,
                        "q_norm": q_norm,
                        "options": options,
                        "site": site,
                        "form_kind": form_kind,
                        "locale": locale,
                    }
                    self.logger.error(
                        f"Strategy execution failed for rule '{rule.get('id')}': {e}. "
                        f"Delegating to LLM fallback.", exc_info=True
                    )
                    # Fall through to LLM delegation
            else:
                self.logger.warning(
                    f"Strategy kind not specified in rule: {rule.get('id')}. "
                    f"Delegating to LLM fallback."
                )
                # Fall through to LLM delegation

        # Step 2: Heuristic fallback (only if no rule was found or rule failed)
        if not rule_found:
            self.logger.info(
                f"[RULES_ENGINE] No rule found, trying heuristics for field_type='{field_type}', q_norm='{q_norm}'"
            )
        heuristic_decision = self._apply_heuristics(q_norm, field_type, options, question)
        if heuristic_decision is not None:
            self.logger.info(f"[RULES_ENGINE] Heuristic decision: {heuristic_decision}")
            return heuristic_decision
        
        # Step 3: LLM Delegation
        if self.llm_delegate:
            # Log when delegating to LLM
            try:
                # Prepare a compact profile summary for logging (avoid huge dumps)
                profile_summary = self.profile.to_json_summary() if hasattr(self.profile, "to_json_summary") else {}
            except Exception:
                profile_summary = {}

            # options may be None or a list; display safely
            opts_display = options if options is not None else []

            # Determine reason for LLM delegation
            if rule_found and rule:
                delegation_reason = f"Rule '{rule.get('id')}' found but failed to produce valid value"
            else:
                delegation_reason = "No matching rule found"

            self.logger.info(
                f"[LLM_DELEGATE] {delegation_reason}. Delegating to LLM. "
                f"question='{question}', field_type='{field_type}', "
                f"q_norm='{q_norm}', options={opts_display}, "
                f"site='{site}', form_kind='{form_kind}', locale='{locale}'"
            )
            
            # Build field_info for LLM
            field_info = {
                "question": question,
                "field_type": field_type,
                "options": options,
                "required": constraints.get("required", True) if constraints and isinstance(constraints, dict) else True,
                "site": site,
                "form_kind": form_kind,
                "locale": locale,
            }
            
            # Add constraints if provided (constraints may contain required, min, max, maxlength, pattern, etc.)
            if constraints and isinstance(constraints, dict):
                field_info.update(constraints)
            
            try:
                # Await the async call to the LLM delegate
                llm_decision = await self.llm_delegate.decide(field_info, self.profile)
                
                # Extract value from LLMDecision object
                if llm_decision and llm_decision.decision != "skip":
                    self.logger.info(f"LLM decision: {llm_decision.value} (confidence={llm_decision.confidence:.2f})")
                    
                    # Process rule generation if learning is enabled
                    skip_rule_generation = rule_failed and rule_found
                    if skip_rule_generation:
                        self.logger.info(
                            "[RULE_GENERATION_SKIPPED] Existing rule '%s' failed (%s); "
                            "skipping auto-learning for this field.",
                            failed_rule_id,
                            failed_rule_reason,
                        )
                    if (
                        self.learning_config.enabled
                        and self.learning_config.auto_learn
                        and not skip_rule_generation
                    ):
                        # Create signature for this field
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
                        
                        # Generate rule using separate request if enabled
                        suggest_rule = None
                        rule_confidence = llm_decision.confidence
                        
                        if self.learning_config.use_separate_rule_generation:
                            try:
                                # Determine delegation reason for rule generation context
                                delegation_reason = f"Rule '{rule.get('id')}' found but failed to produce valid value" if rule_found and rule else "No matching rule found"
                                
                                self.logger.info(
                                    f"[RULE_GENERATION_START] Starting rule generation for field: "
                                    f"question='{question}', field_type='{field_type}', "
                                    f"selected_value='{llm_decision.value}', confidence={llm_decision.confidence:.2f}, "
                                    f"decision='{llm_decision.decision}', reason='{delegation_reason}'"
                                )
                                
                                # Add LLM decision context to field_info for rule generation
                                field_info_for_rule = field_info.copy()
                                field_info_for_rule.update({
                                    "llm_decision": llm_decision.decision,
                                    "llm_confidence": llm_decision.confidence,
                                    "delegation_reason": delegation_reason,
                                    "q_norm": q_norm,  # Normalized question for pattern generation
                                })
                                
                                rule_suggestion = await self.llm_delegate.generate_rule(
                                    field_info=field_info_for_rule,
                                    selected_value=llm_decision.value,
                                    profile=self.profile,
                                    job_context=None  # Can be extended to pass job_context if available
                                )
                                
                                if rule_suggestion:
                                    # Convert RuleSuggestion to suggest_rule format
                                    suggest_rule = {
                                        "q_pattern": rule_suggestion.q_pattern,
                                        "strategy": {
                                            "kind": rule_suggestion.strategy.kind,
                                            "params": rule_suggestion.strategy.params
                                        }
                                    }
                                    rule_confidence = rule_suggestion.confidence
                                    self.logger.info(
                                        f"[RULE_GENERATION_SUCCESS] Rule generated successfully: "
                                        f"pattern='{rule_suggestion.q_pattern}', "
                                        f"strategy={rule_suggestion.strategy.kind}, "
                                        f"strategy_params={rule_suggestion.strategy.params}, "
                                        f"confidence={rule_suggestion.confidence:.2f}"
                                    )
                                else:
                                    self.logger.warning("[RULE_GENERATION_FAILED] Rule generation returned None")
                            except Exception as e:
                                self.logger.error(
                                    f"[RULE_GENERATION_ERROR] Rule generation failed: {e}", 
                                    exc_info=True
                                )
                        
                        # Fallback to suggest_rule from decision if separate generation failed and fallback is enabled
                        if not suggest_rule and self.learning_config.rule_generation_fallback:
                            if llm_decision.suggest_rule and llm_decision.suggest_rule.get("q_pattern"):
                                suggest_rule = llm_decision.suggest_rule
                                self.logger.info(
                                    f"[RULE_GENERATION_FALLBACK] Using suggest_rule from LLM decision as fallback: "
                                    f"pattern='{suggest_rule.get('q_pattern')}', "
                                    f"strategy={suggest_rule.get('strategy', {}).get('kind')}"
                                )
                            else:
                                self.logger.warning(
                                    "[RULE_GENERATION_FALLBACK] Fallback enabled but suggest_rule not available in LLM decision"
                                )
                        
                        # Process the rule if we have one
                        if suggest_rule:
                            # For literal strategies, prefer decision confidence if it's higher
                            # This helps preserve rules that LLM is confident about but rule generation isn't
                            strategy_kind = suggest_rule.get("strategy", {}).get("kind")
                            if strategy_kind in ("literal", "one_of_options"):
                                # Use the decision confidence if it's higher than rule confidence
                                # This handles cases where LLM is confident about the value but rule generation
                                # returns lower confidence due to fallback mechanisms
                                if llm_decision.confidence > rule_confidence:
                                    self.logger.info(
                                        f"[RULE_CONFIDENCE_ADJUST] Using decision confidence {llm_decision.confidence:.2f} "
                                        f"instead of rule confidence {rule_confidence:.2f} for {strategy_kind}"
                                    )
                                    rule_confidence = llm_decision.confidence
                            
                            self.logger.info(
                                f"[RULE_PROCESSING_START] Processing rule suggestion: "
                                f"pattern='{suggest_rule.get('q_pattern')}', "
                                f"strategy={strategy_kind}, "
                                f"confidence={rule_confidence:.2f}"
                            )
                            
                            # Create a temporary LLMDecision-like object with the rule
                            rule_decision = LLMDecision(
                                decision=llm_decision.decision,
                                value=llm_decision.value,
                                confidence=rule_confidence,
                                suggest_rule=suggest_rule
                            )
                            await self._process_suggested_rule(
                                llm_decision=rule_decision,
                                signature=signature
                            )
                        else:
                            self.logger.debug("No rule to process (generation failed and no fallback available)")
                    
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
            self.logger.debug("[RULE_VALIDATION] No rule suggestion from LLM - skipping")
            return
        
        # Check 2: Is confidence sufficient?
        # For literal strategies, use a slightly lower threshold since they're deterministic
        # and the value is known to work
        strategy_kind = suggest_rule.get("strategy", {}).get("kind")
        effective_threshold = self.learning_config.confidence_threshold
        if strategy_kind == "literal":
            # Lower threshold for literal strategies (they're deterministic)
            effective_threshold = max(0.6, self.learning_config.confidence_threshold - 0.15)
            self.logger.debug(
                f"Using lower threshold {effective_threshold:.2f} for literal strategy "
                f"(base threshold: {self.learning_config.confidence_threshold:.2f})"
            )
        
        if confidence < effective_threshold:
            self.logger.warning(
                f"[RULE_VALIDATION_REJECTED] Rule suggestion rejected: confidence {confidence:.2f} "
                f"below threshold {effective_threshold:.2f}. "
                f"Rule: pattern='{suggest_rule.get('q_pattern')}', strategy={strategy_kind}"
            )
            return
        
        # Check 3: Validate structure
        if self.learning_config.enable_pattern_validation or self.learning_config.enable_strategy_validation:
            self.logger.debug(
                f"[RULE_VALIDATION] Validating rule: pattern='{suggest_rule.get('q_pattern')}', "
                f"strategy={suggest_rule.get('strategy', {}).get('kind')}"
            )
            is_valid, error_msg = self.rule_validator.validate(suggest_rule)
            if not is_valid:
                self.logger.warning(
                    f"[RULE_VALIDATION_FAILED] Rule suggestion validation failed: {error_msg}. "
                    f"Rule: pattern='{suggest_rule.get('q_pattern')}', strategy={suggest_rule.get('strategy', {}).get('kind')}"
                )
                return
            else:
                self.logger.debug("[RULE_VALIDATION] Rule validation passed")
            
            # Additional validation: check if params are empty for strategies that require them
            strategy = suggest_rule.get("strategy", {})
            strategy_kind = strategy.get("kind")
            params = strategy.get("params", {})
            
            if strategy_kind:
                strategies_requiring_params = [
                    "one_of_options",
                    "one_of_options_from_profile",
                    "numeric_from_profile",
                    "profile_key"
                ]
                
                if strategy_kind in strategies_requiring_params:
                    is_empty = len(params) == 0
                    
                    # For one_of_options, check if preferred or synonyms is missing
                    if strategy_kind == "one_of_options":
                        is_empty = "preferred" not in params and "synonyms" not in params
                    
                    # For strategies requiring key, check if key is missing
                    elif strategy_kind in ["one_of_options_from_profile", "numeric_from_profile", "profile_key"]:
                        is_empty = "key" not in params or not params.get("key")
                    
                    if is_empty:
                        self.logger.warning(
                            f"Rule suggestion rejected: {strategy_kind} strategy requires params but got empty params. "
                            f"Rule will not be saved."
                        )
                        return
        
        # Check 4: Check for duplicates
        if self.learning_config.enable_duplicate_check:
            q_pattern = suggest_rule.get("q_pattern", "")
            self.logger.debug(f"[RULE_DUPLICATE_CHECK] Checking for duplicates: pattern='{q_pattern}'")
            if self.rule_store.is_duplicate_rule(signature, q_pattern):
                self.logger.info(
                    f"[RULE_DUPLICATE_FOUND] Duplicate rule detected, skipping: pattern='{q_pattern}', "
                    f"field_type='{signature.field_type}'"
                )
                return
            else:
                self.logger.debug("[RULE_DUPLICATE_CHECK] No duplicate found")
        
        # All checks passed - add the rule
        try:
            new_rule = self.rule_store.add_llm_rule(
                signature=signature,
                suggest_rule=suggest_rule,
                confidence=confidence
            )
            
            self.logger.info(
                f"✅ [RULE_SAVED] New rule learned and saved: {new_rule['id']} "
                f"(pattern='{suggest_rule.get('q_pattern')}', strategy={suggest_rule.get('strategy', {}).get('kind')}, "
                f"params={suggest_rule.get('strategy', {}).get('params')}, confidence={confidence:.2f}, "
                f"field_type={signature.field_type}, q_norm='{signature.q_norm}')"
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
    
    def _is_invalid_decision(self, decision: Any, field_type: str, options: Optional[List[str]]) -> bool:
        """
        Check if a decision value is invalid for the given field type.
        
        Args:
            decision: The decision value to validate
            field_type: Type of field (radio, checkbox, select, etc.)
            options: Available options for select/radio fields
            
        Returns:
            True if decision is invalid, False otherwise
        """
        # None is always invalid (handled separately, but check here too)
        if decision is None:
            return True
        
        # For checkbox fields, boolean values (True/False) are always valid
        if field_type == "checkbox" and isinstance(decision, bool):
            return False  # Boolean values are valid for checkboxes
        
        # Convert to string for validation
        # Use explicit None check to avoid treating False as falsy
        if decision is None:
            decision_str = ""
        else:
            decision_str = str(decision).strip()
        
        # Empty string is invalid
        if not decision_str:
            return True
        
        # Check for placeholder/invalid values
        invalid_placeholders = [
            "select an option",
            "choose an option",
            "выберите вариант",
            "выбрать вариант",
        ]
        
        decision_lower = decision_str.lower()
        if decision_lower in invalid_placeholders:
            return True
        
        # For select/radio/combobox fields, decision must be in the options list
        if field_type in ("select", "radio", "combobox") and options:
            # Normalize options and decision for comparison
            options_normalized = [self.normalizer.normalize_string(opt).lower() for opt in options]
            decision_normalized = self.normalizer.normalize_string(decision_str).lower()
            
            # Check if decision matches any option exactly
            if decision_normalized not in options_normalized:
                # Also check if decision is a substring of any option (for partial matches)
                # This handles cases where option might be "Yes, I am willing" and decision is "Yes"
                matches = False
                for opt_norm in options_normalized:
                    # Check if decision is contained in option or vice versa
                    if decision_normalized in opt_norm or opt_norm in decision_normalized:
                        # But exclude very short matches that might be false positives
                        if len(decision_normalized) >= 2 and len(opt_norm) >= 2:
                            matches = True
                            break
                
                if not matches:
                    return True
        
        return False

