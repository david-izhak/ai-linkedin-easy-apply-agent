"""
RuleStore: Persistent storage for form filling rules.

Based on technical specification section 4.3.
"""

import json
import yaml
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

from modal_flow.field_signature import FieldSignature

logger = logging.getLogger(__name__)


class RuleStore:
    """
    Persistent storage for form filling rules with versioning and metadata.
    
    Rules are stored in a single JSON or YAML file with the following structure:
    {
        "schema_version": "1.0",
        "rules": [...]
    }
    
    The file is created automatically with an empty structure if it doesn't exist.
    """
    
    def __init__(self, path: Union[str, Path]):
        """
        Initialize RuleStore with a path to the single rules file.
        
        Args:
            path: Path to rules file (will be created with empty structure if doesn't exist)
        """
        self.path = Path(path)
        self.data: Dict[str, Any] = {"schema_version": "1.0", "rules": []}
        self._load()
    
    def _load(self):
        """
        Load rules from the single rules file.
        
        Creates an empty structure and saves it if the file doesn't exist.
        """
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    # Determine format based on file extension
                    if self.path.suffix.lower() in ['.yaml', '.yml']:
                        self.data = yaml.safe_load(f)
                    else:
                        self.data = json.load(f)
                # Ensure required keys exist
                if "schema_version" not in self.data:
                    self.data["schema_version"] = "1.0"
                if "rules" not in self.data:
                    self.data["rules"] = []
            except (json.JSONDecodeError, yaml.YAMLError, IOError) as e:
                # If file is corrupted, start fresh
                self.data = {"schema_version": "1.0", "rules": []}
        else:
            # Create empty structure
            self.data = {"schema_version": "1.0", "rules": []}
            self.save()
    
    def save(self):
        """Save rules to file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            # Determine format based on file extension
            if self.path.suffix.lower() in ['.yaml', '.yml']:
                yaml.dump(self.data, f, allow_unicode=True, indent=2, default_flow_style=False)
            else:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def find(self, signature: FieldSignature) -> Optional[Dict[str, Any]]:
        """
        Find a matching rule for the given field signature.
        
        Matching logic:
        - site must match (or be "*")
        - field_type must match exactly
        - q_pattern must match (regex or substring) against q_norm
        - options_fingerprint must match (if provided)
        
        Returns:
            First matching rule dict, or None if no match found
        """
        q_norm_lower = signature.q_norm.lower()
        
        for rule in self.data.get("rules", []):
            rule_scope = rule.get("scope", {})
            rule_sig = rule.get("signature", {})
            rule_id = rule.get("id", "unknown")
            
            # Check site scope
            site = rule_scope.get("site", "*")
            if site != "*" and site != signature.site:
                continue
            
            # Check field type
            if rule_sig.get("field_type") != signature.field_type:
                continue
            
            # Check question pattern using a reliable regex match
            q_pattern = rule_sig.get("q_pattern", "").strip()
            if q_pattern:
                import re
                try:
                    # Always perform a case-insensitive regex search
                    match = re.search(q_pattern, signature.q_norm, re.IGNORECASE)
                    logger.debug(
                        f"[RuleStore.find] Rule '{rule_id}': pattern='{q_pattern}', "
                        f"q_norm='{signature.q_norm}', match={bool(match)}"
                    )
                    if not match:
                        continue
                except re.error as e:
                    # If the pattern is an invalid regex, log it and skip the rule
                    logger.warning(
                        f"[RuleStore.find] Invalid regex pattern '{q_pattern}' in rule '{rule_id}'. Error: {e}"
                    )
                    continue
            
            # Check options fingerprint (if provided)
            opts_fp = rule_sig.get("options_fingerprint")
            if opts_fp and opts_fp != signature.opts_fp:
                continue
            
            # Match found!
            logger.info(
                f"[RuleStore.find] Rule '{rule_id}' matched! "
                f"field_type='{signature.field_type}', q_norm='{signature.q_norm}'"
            )
            return rule
        
        logger.debug(
            f"[RuleStore.find] No rule found for field_type='{signature.field_type}', "
            f"q_norm='{signature.q_norm}', opts_fp='{signature.opts_fp}'"
        )
        return None
    
    def is_duplicate_rule(
        self, 
        signature: FieldSignature, 
        new_q_pattern: str
    ) -> bool:
        """
        Check if a similar rule already exists in the store.
        
        Prevents duplicate rules by checking for existing rules with:
        - Same field_type
        - Same or very similar q_pattern
        
        Args:
            signature: Field signature for the new rule
            new_q_pattern: Pattern of the new rule to check
            
        Returns:
            True if a duplicate is found, False otherwise
        
        Example:
            >>> signature = FieldSignature(field_type="checkbox", ...)
            >>> is_dup = rule_store.is_duplicate_rule(signature, "(python|питон)")
            >>> if is_dup:
            ...     print("Rule already exists")
        """
        new_pattern_lower = new_q_pattern.lower().strip()
        
        for rule in self.data.get("rules", []):
            rule_sig = rule.get("signature", {})
            
            # Check field_type match
            if rule_sig.get("field_type") != signature.field_type:
                continue
            
            existing_pattern = rule_sig.get("q_pattern", "").strip()
            
            # Exact match (case-insensitive)
            if existing_pattern.lower() == new_pattern_lower:
                return True
        
        return False
    
    def add_llm_rule(
        self,
        signature: FieldSignature,
        suggest_rule: Dict[str, Any],
        confidence: float
    ) -> Dict[str, Any]:
        """
        Add a new rule generated by LLM to the store.
        
        Args:
            signature: Field signature for the rule
            suggest_rule: Rule suggestion from LLM (contains q_pattern and strategy)
            confidence: Confidence score from LLM (0.0 to 1.0)
            
        Returns:
            The created rule dict
        """
        rule_id = f"rls_{int(time.time())}"
        
        rule = {
            "id": rule_id,
            "scope": {
                "site": signature.site,
                "form_kind": signature.form_kind,
                "locale": [signature.locale]
            },
            "signature": {
                "field_type": signature.field_type,
                "q_pattern": suggest_rule.get("q_pattern", ""),
                "options_fingerprint": signature.opts_fp
            },
            "strategy": suggest_rule.get("strategy", {}),
            "constraints": {
                "required": True
            },
            "meta": {
                "source": "llm",
                "confidence": confidence,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "last_seen": None,
                "hits": 0
            }
        }
        
        self.data["rules"].append(rule)
        self.save()
        logger.info(
            f"[RuleStore.add_llm_rule] Rule '{rule_id}' added to store. "
            f"Total rules: {len(self.data['rules'])}"
        )
        return rule
