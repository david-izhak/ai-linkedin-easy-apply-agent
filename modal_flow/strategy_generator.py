"""
Client-side strategy generation for rule suggestions.

This module generates strategy definitions based on field information
and selected values, serving as a fallback when LLM doesn't provide strategy.
"""

import re
import logging
from typing import Dict, Any, Optional, List

from modal_flow.llm_delegate import StrategyDefinition
from modal_flow.profile_schema import CandidateProfile


logger = logging.getLogger(__name__)


class StrategyGenerator:
    """Generates strategy definitions based on field context."""
    
    # Common profile keys mapping
    PROFILE_KEY_MAPPINGS = {
        "email": "email",
        "e-mail": "email",
        "phone": "phone",
        "telephone": "phone",
        "mobile": "phone",
        "city": "address.city",
        "location": "address.city",
        "country": "address.country",
        "first name": "personal.firstName",
        "firstname": "personal.firstName",
        "last name": "personal.lastName",
        "lastname": "personal.lastName",
        "github": "links.github",
        "linkedin": "links.linkedin",
        "website": "links.website",
        "portfolio": "links.portfolio",
    }
    
    # Technology/skill keywords for years_experience
    # Note: keys should match the keys in profile.years_experience
    TECHNOLOGY_KEYWORDS = [
        "python", "java", "javascript", "typescript", "go", "rust", "c++", "c#",
        "aws", "azure", "gcp", "kubernetes", "docker", "kafka", "mongodb",
        "postgresql", "mysql", "redis", "elasticsearch", "spark", "node.js", "node_js",
        "react", "angular", "vue", "spring", "django", "flask", "tensorflow",
        "pytorch", "terraform", "ansible", "jenkins", "gitlab", "github",
        "amazon web services", "amazon web services (aws)"
    ]
    
    # Mapping for technology names to profile keys
    TECHNOLOGY_KEY_MAPPING = {
        "amazon web services": "aws",
        "amazon web services (aws)": "aws",
        "node.js": "node_js",
        "node js": "node_js",
        "c++": "cplusplus",
        "c#": "csharp",
    }
    
    def generate_strategy(
        self,
        field_info: Dict[str, Any],
        selected_value: Any,
        profile: CandidateProfile,
        question: Optional[str] = None
    ) -> Optional[StrategyDefinition]:
        """
        Generate strategy definition based on field context.
        
        Args:
            field_info: Field information dictionary
            selected_value: The value that was selected
            profile: Candidate profile
            question: Field question text (optional, extracted from field_info if not provided)
            
        Returns:
            StrategyDefinition if strategy can be generated, None otherwise
        """
        field_type = field_info.get("field_type", "").lower()
        question = question or field_info.get("question", "")
        options = field_info.get("options", [])
        
        # Checkbox fields
        if field_type == "checkbox":
            return self._generate_checkbox_strategy(selected_value)
        
        # Radio/Select fields
        if field_type in ("radio", "select", "multiselect"):
            return self._generate_radio_select_strategy(selected_value, options, question, profile)
        
        # Number fields
        if field_type == "number":
            return self._generate_number_strategy(question, selected_value, profile)
        
        # Text fields
        if field_type == "text":
            return self._generate_text_strategy(question, selected_value, profile)
        
        # Combobox fields
        if field_type == "combobox":
            return self._generate_combobox_strategy(question, selected_value, profile)
        
        logger.warning(f"Unknown field type: {field_type}, cannot generate strategy")
        return None
    
    def _generate_checkbox_strategy(self, selected_value: Any) -> StrategyDefinition:
        """Generate strategy for checkbox fields."""
        value = bool(selected_value) if selected_value is not None else True
        return StrategyDefinition(
            kind="literal",
            params={"value": value}
        )
    
    def _generate_radio_select_strategy(
        self,
        selected_value: Any,
        options: List[str],
        question: Optional[str] = None,
        profile: Optional[CandidateProfile] = None
    ) -> StrategyDefinition:
        """Generate strategy for radio/select fields."""
        question_lower = (question or "").lower()
        
        # Check if this is a profile-based field (language, gender, work authorization, etc.)
        if profile and question:
            # Try to determine if this is a profile-based field
            profile_based_key = self._detect_profile_key_for_radio_select(question, selected_value, options, profile)
            if profile_based_key:
                # Generate one_of_options_from_profile strategy
                synonyms = self._generate_synonyms_for_profile_value(profile_based_key, selected_value, options, profile)
                params = {"key": profile_based_key}
                if synonyms:
                    params["synonyms"] = synonyms
                return StrategyDefinition(
                    kind="one_of_options_from_profile",
                    params=params
                )
        
        # For simple radio/select fields, use one_of_options
        # Check if selected_value is in options (exact match)
        if selected_value and selected_value in options:
            return StrategyDefinition(
                kind="one_of_options",
                params={"preferred": [str(selected_value)]}
            )
        
        # If selected_value not in options, try to find case-insensitive match
        if selected_value:
            selected_str = str(selected_value).strip().lower()
            for option in options:
                option_clean = str(option).strip().lower()
                if selected_str == option_clean:
                    return StrategyDefinition(
                        kind="one_of_options",
                        params={"preferred": [option]}  # Use original option with correct case
                    )
        
        # Fallback: use selected_value if available, otherwise first option
        if selected_value:
            preferred = [str(selected_value)]
        elif options:
            preferred = [options[0]]
        else:
            preferred = []
        
        return StrategyDefinition(
            kind="one_of_options",
            params={"preferred": preferred}
        )
    
    def _detect_profile_key_for_radio_select(
        self,
        question: str,
        selected_value: Any,
        options: List[str],
        profile: CandidateProfile
    ) -> Optional[str]:
        """Detect if this radio/select field should use profile data."""
        question_lower = question.lower()
        
        # Language-related questions
        if "language" in question_lower or "speaker" in question_lower:
            if hasattr(profile, 'languages') and profile.languages:
                selected_str = str(selected_value).lower()
                question_lower_for_lang = question_lower
                
                # For native speaker questions, find languages with Native proficiency
                if "native" in question_lower_for_lang:
                    for i, lang in enumerate(profile.languages):
                        if isinstance(lang, dict):
                            lang_name = lang.get("language", "").lower()
                            proficiency = lang.get("proficiency", "").lower()
                            
                            # Check if this is a native language and matches the question
                            if "native" in proficiency:
                                # Check if language name is mentioned in question
                                if lang_name in question_lower_for_lang or any(
                                    word in question_lower_for_lang for word in lang_name.split()
                                ):
                                    return f"languages[{i}].language"
                                # Also check selected value
                                if lang_name in selected_str or selected_str in lang_name:
                                    return f"languages[{i}].language"
                    
                    # If no native language found matching question, return first native language
                    for i, lang in enumerate(profile.languages):
                        if isinstance(lang, dict):
                            proficiency = lang.get("proficiency", "").lower()
                            if "native" in proficiency:
                                return f"languages[{i}].language"
                
                # For non-native questions, check if selected value matches any language
                for i, lang in enumerate(profile.languages):
                    if isinstance(lang, dict):
                        lang_name = lang.get("language", "").lower()
                    else:
                        lang_name = str(lang).lower()
                    
                    # Check if this language matches the selected value or question
                    if lang_name in selected_str or selected_str in lang_name:
                        return f"languages[{i}].language"
                    # Also check if language name appears in question
                    if lang_name in question_lower_for_lang:
                        return f"languages[{i}].language"
                
                # Default to first language if no match found
                return "languages[0].language"
        
        # Gender questions
        if "gender" in question_lower or "identify" in question_lower:
            if hasattr(profile, 'equalOpportunity') and profile.equalOpportunity:
                return "equalOpportunity.gender"
        
        # Work authorization questions
        if "visa" in question_lower or "authorization" in question_lower or "citizen" in question_lower:
            if "us" in question_lower or "united states" in question_lower:
                return "work_authorization.US"
            elif "eu" in question_lower or "europe" in question_lower:
                return "work_authorization.EU"
            elif "il" in question_lower or "israel" in question_lower:
                return "work_authorization.IL"
        
        # Employment history questions
        if "palo alto" in question_lower:
            return "previous_employment.palo_alto_networks"
        if "navan" in question_lower:
            return "previous_employment.navan"
        
        # Future opportunities
        if "future" in question_lower and "opportunit" in question_lower:
            return "future_opportunities_willingness"
        
        return None
    
    def _generate_synonyms_for_profile_value(
        self,
        profile_key: str,
        selected_value: Any,
        options: List[str],
        profile: CandidateProfile
    ) -> Optional[Dict[str, List[str]]]:
        """Generate synonyms map for profile-based radio/select fields."""
        # Get profile value
        profile_value = profile.get_nested_value(profile_key)
        if profile_value is None:
            return None
        
        profile_value_str = str(profile_value)
        selected_str = str(selected_value).lower()
        
        # Language synonyms - build from actual profile languages
        if "languages" in profile_key:
            synonyms = {}
            if hasattr(profile, 'languages') and profile.languages:
                # Language name to Russian translation mapping
                lang_translations = {
                    "english": "английский",
                    "hebrew": "иврит",
                    "russian": "русский",
                    "spanish": "испанский",
                    "french": "французский",
                    "german": "немецкий",
                    "chinese": "китайский",
                    "japanese": "японский"
                }
                
                for lang in profile.languages:
                    if isinstance(lang, dict):
                        lang_name = lang.get("language", "")
                    else:
                        lang_name = str(lang)
                    
                    if not lang_name:
                        continue
                    
                    # Create synonyms for this language
                    lang_lower = lang_name.lower()
                    lang_synonyms = [
                        lang_name,  # Original name
                        lang_name.lower(),  # Lowercase
                        lang_name.capitalize(),  # Capitalized
                        lang_name.upper()  # Uppercase
                    ]
                    
                    # Add Russian translation if available
                    if lang_lower in lang_translations:
                        lang_synonyms.append(lang_translations[lang_lower])
                        lang_synonyms.append(lang_translations[lang_lower].capitalize())
                    
                    # Add common variations
                    if "english" in lang_lower:
                        lang_synonyms.extend(["English", "EN", "en"])
                    elif "hebrew" in lang_lower:
                        lang_synonyms.extend(["Hebrew", "HE", "he", "иврит"])
                    elif "russian" in lang_lower:
                        lang_synonyms.extend(["Russian", "RU", "ru", "русский"])
                    
                    synonyms[lang_name] = list(set(lang_synonyms))  # Remove duplicates
            
            # If no languages found, use default
            if not synonyms:
                synonyms = {
                    "English": ["English", "английский", "english", "EN", "en"],
                    "Hebrew": ["Hebrew", "иврит", "hebrew", "HE", "he"],
                    "Russian": ["Russian", "русский", "russian", "RU", "ru"]
                }
            
            return synonyms
        
        # Gender synonyms
        if "gender" in profile_key:
            return {
                "Male": ["Male", "Мужской", "male"],
                "Female": ["Female", "Женский", "female"],
                "Decline": ["Decline", "Prefer not to say", "Не указывать", "decline"]
            }
        
        # Work authorization synonyms
        if "work_authorization" in profile_key:
            return {
                "yes": ["Yes", "Да", "yes", "U.S. Citizen", "Citizen"],
                "no": ["No", "Нет", "no"],
                "need_visa": ["Need Visa", "Требуется виза", "need visa", "Visa Required"]
            }
        
        # Employment synonyms
        if "previous_employment" in profile_key:
            return {
                "no": ["No", "Нет", "no", "No - I have not worked for", "I have not worked for"],
                "yes": ["Yes", "Да", "yes", "I have worked for"]
            }
        
        # Future opportunities synonyms
        if "future_opportunities" in profile_key:
            return {
                "Yes": ["Yes", "Да", "yes"],
                "No": ["No", "Нет", "no"]
            }
        
        # Default: create simple synonyms based on selected value and options
        synonyms = {}
        for option in options:
            option_lower = option.lower()
            # Try to match with profile value
            if profile_value_str.lower() in option_lower or option_lower in profile_value_str.lower():
                synonyms[profile_value_str] = [option, option_lower, option_lower.capitalize()]
                break
        
        return synonyms if synonyms else None
    
    def _generate_number_strategy(
        self,
        question: str,
        selected_value: Any,
        profile: CandidateProfile
    ) -> Optional[StrategyDefinition]:
        """Generate strategy for number fields (typically years of experience)."""
        # Try to extract technology/skill from question
        question_lower = question.lower()
        
        # Look for technology keywords
        for tech in self.TECHNOLOGY_KEYWORDS:
            if tech in question_lower:
                # Map technology name to profile key
                tech_key = self.TECHNOLOGY_KEY_MAPPING.get(tech, tech)
                # Normalize technology name (e.g., "node.js" -> "node_js")
                tech_key = tech_key.replace(".", "_").replace("+", "plus").replace("#", "sharp").replace(" ", "_").lower()
                key_path = f"years_experience.{tech_key}"
                
                # Verify key exists in profile
                if profile.get_nested_value(key_path) is not None:
                    return StrategyDefinition(
                        kind="numeric_from_profile",
                        params={"key": key_path}
                    )
                # Try with original tech name
                tech_key_orig = tech.replace(".", "_").replace("+", "plus").replace("#", "sharp").replace(" ", "_").lower()
                key_path_orig = f"years_experience.{tech_key_orig}"
                if profile.get_nested_value(key_path_orig) is not None:
                    return StrategyDefinition(
                        kind="numeric_from_profile",
                        params={"key": key_path_orig}
                    )
        
        # Try to extract skill name using regex
        # Pattern: "years of experience with X" or "experience with X"
        patterns = [
            r"years?\s+of\s+experience\s+with\s+([a-zA-Z0-9\s\+\.#]+)",
            r"experience\s+with\s+([a-zA-Z0-9\s\+\.#]+)",
            r"years?\s+of\s+([a-zA-Z0-9\s\+\.#]+)\s+experience",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question_lower, re.IGNORECASE)
            if match:
                tech = match.group(1).strip()
                # Normalize
                tech_key = tech.replace(" ", "_").replace(".", "_").replace("+", "plus").replace("#", "sharp").lower()
                key_path = f"years_experience.{tech_key}"
                
                if profile.get_nested_value(key_path) is not None:
                    return StrategyDefinition(
                        kind="numeric_from_profile",
                        params={"key": key_path}
                    )
        
        # If cannot determine key, return None (let LLM handle it)
        logger.debug(f"Cannot determine profile key for number field: {question}")
        return None
    
    def _generate_text_strategy(
        self,
        question: str,
        selected_value: Any,
        profile: CandidateProfile
    ) -> Optional[StrategyDefinition]:
        """Generate strategy for text fields."""
        question_lower = question.lower()
        selected_str = str(selected_value).lower() if selected_value else ""
        
        # Check if selected value matches a profile field directly
        if selected_value:
            # Try direct profile keys
            for key, profile_key in self.PROFILE_KEY_MAPPINGS.items():
                if key in question_lower:
                    if profile.get_nested_value(profile_key) is not None:
                        return StrategyDefinition(
                            kind="profile_key",
                            params={"key": profile_key}
                        )
        
        # Check question for common patterns
        for key, profile_key in self.PROFILE_KEY_MAPPINGS.items():
            if key in question_lower:
                if profile.get_nested_value(profile_key) is not None:
                    return StrategyDefinition(
                        kind="profile_key",
                        params={"key": profile_key}
                    )
        
        # Check if selected value matches profile email or phone
        if selected_value:
            profile_email = profile.email
            profile_phone = profile.phone
            
            if profile_email and selected_str == profile_email.lower():
                return StrategyDefinition(
                    kind="profile_key",
                    params={"key": "email"}
                )
            
            if profile_phone and selected_str == profile_phone.lower():
                return StrategyDefinition(
                    kind="profile_key",
                    params={"key": "phone"}
                )
        
        # For text fields that don't match profile keys, use literal strategy with selected_value
        # This handles cases like "referral", "message to hiring manager", etc.
        logger.debug(
            f"Cannot determine profile key for text field: {question}. "
            f"Will use literal strategy with selected_value if provided."
        )
        # Return None to let the caller handle it (may use literal strategy as fallback)
        return None
    
    def _generate_combobox_strategy(
        self,
        question: str,
        selected_value: Any,
        profile: CandidateProfile
    ) -> Optional[StrategyDefinition]:
        """Generate strategy for combobox fields (typically location)."""
        question_lower = question.lower()
        
        # Location fields - use get_nested_value for safe access
        if "location" in question_lower or "city" in question_lower:
            city_value = profile.get_nested_value("address.city")
            if city_value is not None:
                return StrategyDefinition(
                    kind="profile_key",
                    params={"key": "address.city"}
                )
            # Also check country
            country_value = profile.get_nested_value("address.country")
            if country_value is not None:
                return StrategyDefinition(
                    kind="profile_key",
                    params={"key": "address.country"}
                )
        
        # Fallback to text strategy
        return self._generate_text_strategy(question, selected_value, profile)

