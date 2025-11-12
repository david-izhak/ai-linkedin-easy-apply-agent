"""
QuestionNormalizer: Normalize and classify form field questions.

Based on creative phase design document.
"""

import re
from typing import List, Optional, Dict, Set
from rapidfuzz import process, fuzz


class QuestionNormalizer:
    """
    Normalizes question text and provides utilities for question classification
    and option matching.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize QuestionNormalizer with configuration.
        
        Args:
            config_path: Optional path to YAML config file with synonyms and keywords.
                        If None, uses default built-in rules.
        """
        self.synonyms: Dict[str, List[str]] = {}
        self.type_keywords: Dict[str, Set[str]] = {}
        self.skill_synonyms: Dict[str, List[str]] = {}
        self.currency_synonyms: Dict[str, List[str]] = {}
        self._skill_synonyms_map: Dict[str, str] = {}  # Reverse map for quick lookup
        self._load_config(config_path)
    
    def _load_config(self, config_path: Optional[str]):
        """Load configuration from YAML file or use defaults."""
        try:
            if not config_path:
                raise FileNotFoundError()
            
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            
            self.synonyms = config.get("synonyms", {})
            type_kw = config.get("type_keywords", {})
            self.type_keywords = {k: set(v) for k, v in type_kw.items()}
            self.skill_synonyms = config.get("skill_synonyms", {})
            self.currency_synonyms = config.get("currency_synonyms", {})
        
        except Exception:
            self._load_defaults()
        
        finally:
            # Always build the map
            self._build_skill_synonyms_map()

    def _load_defaults(self):
        """Load default synonym and keyword mappings."""
        self.synonyms = {
            "YES": ["да", "y", "authorized", "i am authorized", "i confirm", "yes"],
            "NO": ["нет", "n", "not authorized", "no"],
        }
        
        self.type_keywords = {
            "QUANTITY_YEARS": {"year", "years", "experience", "опыт"},
            "SALARY": {"salary", "compensation", "зарплата"},
            "LOCATION": {"location", "city", "country", "локация", "город"},
            "BOOLEAN": {"are you", "do you", "have you", "can you", "вы", "у вас"},
        }
        self.skill_synonyms = {}
        self.currency_synonyms = {}
        # The map will be built in _load_config after this call

    def _build_skill_synonyms_map(self):
        """Build a reverse map from synonym to canonical name for quick lookup."""
        self._skill_synonyms_map = {}
        for canonical, synonyms in self.skill_synonyms.items():
            for synonym in synonyms:
                normalized_synonym = self.normalize_text(synonym)
                self._skill_synonyms_map[normalized_synonym] = canonical

    def normalize_text(self, text: str) -> str:
        """
        Clean and normalize text for comparison.
        
        Steps:
        1. Convert to lowercase
        2. Remove HTML tags
        3. Remove special characters and punctuation (keep spaces)
        4. Collapse multiple whitespace to single space
        5. Trim leading/trailing whitespace
        
        Args:
            text: Raw text to normalize
            
        Returns:
            Normalized text string
        """
        if not text:
            return ""
        
        # Convert to string if not already
        if not isinstance(text, str):
            text = str(text)
        
        # Convert to lowercase
        normalized = text.lower()
        
        # Remove HTML tags
        normalized = re.sub(r"<[^>]+>", "", normalized)
        
        # Remove special characters and punctuation, keep alphanumeric and spaces
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized)
        
        # Trim
        normalized = normalized.strip()

        # Deduplicate repeated halves (common for duplicated legends + labels)
        normalized = self._deduplicate_repeated_text(normalized)
        
        return normalized

    def _deduplicate_repeated_text(self, text: str) -> str:
        """
        Collapse strings composed of repeated halves into a single occurrence.
        """
        current = text
        while current:
            tokens = current.split()
            if len(tokens) % 2 != 0 or not tokens:
                break
            midpoint = len(tokens) // 2
            first_half = tokens[:midpoint]
            second_half = tokens[midpoint:]
            if first_half != second_half:
                break
            reduced = " ".join(first_half)
            if reduced == current:
                break
            current = reduced
        return current

    def normalize_string(self, text: str) -> str:
        """
        Полностью очищает строку: убирает крайние пробелы и схлопывает внутренние.
        """
        if not isinstance(text, str):
            return ""
        stripped = text.strip()
        normalized = re.sub(r'\s+', ' ', stripped)
        return normalized
    
    def get_question_type(self, question: str) -> str:
        """
        Detect the semantic type of a question.
        
        Args:
            question: Raw question text
            
        Returns:
            Question type string (e.g., "QUANTITY_YEARS", "SALARY", "BOOLEAN", "UNKNOWN")
        """
        q_norm = self.normalize_text(question)
        tokens = set(q_norm.split())
        
        # Check each type's keywords
        for q_type, keywords in self.type_keywords.items():
            if keywords.intersection(tokens):
                return q_type
        
        return "UNKNOWN"
    
    def normalize_options(self, options: List[str]) -> List[str]:
        """
        Normalize a list of option strings.
        
        Args:
            options: List of raw option strings
            
        Returns:
            List of normalized option strings
        """
        return [self.normalize_text(opt) for opt in options]
    
    def map_to_canonical(self, value: str) -> str:
        """
        Map a value to its canonical form using synonym dictionary.
        
        Args:
            value: Value to map (e.g., "Да")
            
        Returns:
            Canonical form (e.g., "YES") or normalized original if no mapping found
        """
        normalized = self.normalize_text(value)
        
        # Check each canonical form and its synonyms
        for canonical, syns in self.synonyms.items():
            if normalized == self.normalize_text(canonical):
                return canonical
            for syn in syns:
                if normalized == self.normalize_text(syn):
                    return canonical
        
        # No mapping found, return normalized original
        return normalized
    
    def map_skill_to_canonical(self, skill_name: str) -> str:
        """
        Map a skill name to its canonical form using the skill_synonyms dictionary.
        
        Args:
            skill_name: The skill name from the form (normalized).
            
        Returns:
            The canonical skill name if a synonym is found, otherwise the original skill name.
        """
        return self._skill_synonyms_map.get(skill_name, skill_name)
    
    def find_best_match(
        self,
        target: str,
        choices: List[str],
        threshold: int = 85
    ) -> Optional[str]:
        """
        Find the best matching option using fuzzy matching.

        Args:
            target: Target value to match
            choices: List of available choices
            threshold: Minimum similarity score (0-100) to consider a match

        Returns:
            Best matching choice, or None if no match above threshold
        """
        if not choices:
            return None

        # Use token_set_ratio for robust matching (handles word order)
        result = process.extractOne(
            target,
            choices,
            scorer=fuzz.token_set_ratio,
            score_cutoff=threshold
        )

        if result:
            matched_value, score = result
            return matched_value

        return None

    def detect_currency(self, text: str, raw_text: Optional[str] = None) -> Optional[str]:
        """
        Detect currency canonical key (e.g. 'usd', 'eur', 'nis') mentioned in the text.

        Strategy:
        - Check for explicit currency symbol in raw_text (e.g. $, €, ₪)
        - Normalize text and look for synonyms defined in `currency_synonyms`

        Args:
            text: Normalized text (usually from normalize_text)
            raw_text: Original raw text (optional) to check for symbols

        Returns:
            Canonical currency key (lowercase) or None if not found
        """
        if not text and not raw_text:
            return None

        # Check common currency symbols first in raw_text
        if raw_text:
            if "$" in raw_text:
                return "usd"
            if "€" in raw_text:
                return "eur"
            if "₪" in raw_text or "nis" in raw_text.lower():
                # treat explicit nis or shekel symbol as nis
                return "nis"

        # Fallback: search normalized text for synonyms
        text_norm = text or self.normalize_text(raw_text or "")
        # Ensure currency_synonyms is present
        for canonical, syns in (self.currency_synonyms or {}).items():
            for syn in syns:
                syn_norm = self.normalize_text(str(syn))
                if not syn_norm:
                    continue
                # match as whole token or substring
                if syn_norm in text_norm.split() or syn_norm in text_norm:
                    return canonical.lower()

        return None
