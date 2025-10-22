import logging
from .base import BaseStrategy
from ..normalizer import QuestionNormalizer
from ..profile_schema import CandidateProfile


class SalaryByCurrencyStrategy(BaseStrategy):
    """
    A strategy to determine the salary value based on the currency mentioned
    in the question text. It uses a template for the profile key and falls
    back to a default currency if no specific currency is found.
    """

    def __init__(self, params: dict, normalizer: QuestionNormalizer, logger=None):
        """
        Initializes the strategy with parameters and a question normalizer.
        :param params: A dictionary containing 'base_key_template' and an optional 'default_currency'.
        :param normalizer: An instance of QuestionNormalizer to identify currency synonyms.
        :param logger: Optional logger instance.
        """
        super().__init__(params)
        self.normalizer = normalizer
        self.base_key_template = self.params.get("base_key_template")
        self.default_currency = self.params.get("default_currency", "nis")
        self.logger = logger or logging.getLogger(__name__)

    def get_value(self, profile: CandidateProfile, a_field: dict) -> str | None:
        """
        Retrieves the salary value from the profile, adjusted for currency.
        :param profile: The user's profile data.
        :param a_field: The field dictionary containing the question text.
        :return: The salary as a string, or None if not found.
        """
        question_text = a_field.get("question", "")
        # Normalize the question text to match against currency synonyms
        question_normalized = self.normalizer.normalize_text(question_text)
        self.logger.info(f"[SalaryByCurrencyStrategy] Original question: '{question_text}'")
        self.logger.info(f"[SalaryByCurrencyStrategy] Normalized question: '{question_normalized}'")
        self.logger.info(f"[SalaryByCurrencyStrategy] Available currency_synonyms: {list(self.normalizer.currency_synonyms.keys())}")

        currency = self.default_currency
        for canonical, synonyms in self.normalizer.currency_synonyms.items():
            self.logger.debug(f"[SalaryByCurrencyStrategy] Checking currency '{canonical}' with synonyms: {synonyms}")
            # Check both normalized question and original (lowercased) for currency synonyms
            for synonym in synonyms:
                synonym_lower = synonym.lower()
                if synonym_lower in question_normalized or synonym_lower in question_text.lower():
                    currency = canonical
                    self.logger.info(f"[SalaryByCurrencyStrategy] Currency detected: '{currency}' (matched synonym '{synonym}')")
                    break
            if currency != self.default_currency:
                break

        if currency == self.default_currency:
            self.logger.info(f"[SalaryByCurrencyStrategy] No currency found in question, using default: '{currency}'")

        profile_key = self.base_key_template.format(currency=currency)
        self.logger.info(f"[SalaryByCurrencyStrategy] Profile key: '{profile_key}'")
        value = profile.get_nested_value(profile_key)
        self.logger.info(f"[SalaryByCurrencyStrategy] Retrieved value: {value} for key '{profile_key}'")

        return str(value) if value is not None else None
