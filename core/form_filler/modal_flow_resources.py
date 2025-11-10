import logging
from pathlib import Path
from typing import Optional

from config import ModalFlowConfig, LLMSettings
from llm.llm_client import LLMClient
from modal_flow.learning_config import LearningConfig
from modal_flow.llm_delegate_openai import OpenAILLMDelegate
from modal_flow.normalizer import QuestionNormalizer
from modal_flow.profile_schema import CandidateProfile
from modal_flow.profile_store import ProfileStore
from modal_flow.rules_store import RuleStore


class ModalFlowResources:
    """Lazy loader for modal flow dependencies (profile, rules, normalizer, LLM)."""

    def __init__(
        self,
        modal_flow_config: ModalFlowConfig,
        llm_config: LLMSettings,
        logger: Optional[logging.Logger] = None,
    ):
        self._modal_flow_config = modal_flow_config
        self._llm_config = llm_config
        self._logger = logger or logging.getLogger(__name__)

        self._profile: Optional[CandidateProfile] = None
        self._rule_store: Optional[RuleStore] = None
        self._normalizer: Optional[QuestionNormalizer] = None
        self._learning_config: Optional[LearningConfig] = None
        self._llm_delegate: Optional[OpenAILLMDelegate] = None
        self._llm_client: Optional[LLMClient] = None

    @property
    def profile(self) -> CandidateProfile:
        if self._profile is None:
            profile_path = Path(self._modal_flow_config.profile_path)
            self._logger.debug("Loading candidate profile from %s", profile_path)
            store = ProfileStore(profile_path)
            self._profile = store.load()
        return self._profile

    @property
    def rule_store(self) -> RuleStore:
        if self._rule_store is None:
            rules_path = Path(self._modal_flow_config.rules_path)
            self._logger.debug("Loading rules from %s", rules_path)
            self._rule_store = RuleStore(rules_path)
        return self._rule_store

    @property
    def normalizer(self) -> QuestionNormalizer:
        if self._normalizer is None:
            config_path = self._modal_flow_config.normalizer_rules_path
            config_arg = str(config_path) if config_path else None
            self._logger.debug("Loading normalizer with config %s", config_arg)
            self._normalizer = QuestionNormalizer(config_arg)
        return self._normalizer

    @property
    def learning_config(self) -> LearningConfig:
        if self._learning_config is None:
            cfg = self._modal_flow_config.learning
            self._learning_config = LearningConfig(
                enabled=cfg.enabled,
                auto_learn=cfg.auto_learn,
                use_separate_rule_generation=cfg.use_separate_rule_generation,
                rule_generation_fallback=cfg.rule_generation_fallback,
                confidence_threshold=cfg.confidence_threshold,
                enable_duplicate_check=cfg.enable_duplicate_check,
                enable_pattern_validation=cfg.enable_pattern_validation,
                enable_strategy_validation=cfg.enable_strategy_validation,
                review_mode=cfg.review_mode,
                review_path=str(cfg.review_path) if cfg.review_path else None,
            )
        return self._learning_config

    @property
    def llm_delegate(self) -> Optional[OpenAILLMDelegate]:
        if not self._modal_flow_config.llm_delegate_enabled:
            return None

        if self._llm_delegate is None:
            self._logger.debug("Initializing modal flow LLM delegate")
            self._llm_delegate = OpenAILLMDelegate(self._get_llm_client())
        return self._llm_delegate

    def _get_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._logger.debug("Creating LLM client for modal flow")
            self._llm_client = LLMClient(self._llm_config)
        return self._llm_client

    def reset(self) -> None:
        """Reset cached resources (useful for tests)."""
        self._profile = None
        self._rule_store = None
        self._normalizer = None
        self._learning_config = None
        self._llm_delegate = None
        self._llm_client = None
