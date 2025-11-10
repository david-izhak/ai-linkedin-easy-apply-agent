"""
Modal Flow Engine - Main package initialization with lazy exports.
"""

from importlib import import_module
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    # Явные импорты только для статического анализа / IDE
    from .modal_flow import ModalFlowRunner, ModalFlowRunResult
    from .profile_store import ProfileStore
    from .rules_store import RuleStore
    from .rules_engine import RulesEngine
    from .normalizer import QuestionNormalizer
    from .field_signature import FieldSignature
    from .profile_schema import CandidateProfile
    from .llm_delegate import BaseLLMDelegate, LLMDecision
    from .llm_delegate_openai import OpenAILLMDelegate

__all__ = [
    "ModalFlowRunner",
    "ProfileStore",
    "RuleStore",
    "RulesEngine",
    "QuestionNormalizer",
    "FieldSignature",
    "CandidateProfile",
    "BaseLLMDelegate",
    "LLMDecision",
    "OpenAILLMDelegate",
    "ModalFlowRunResult",
]

_LAZY_IMPORTS = {
    "ModalFlowRunner": "modal_flow.modal_flow",
    "ModalFlowRunResult": "modal_flow.modal_flow",
    "ProfileStore": "modal_flow.profile_store",
    "RuleStore": "modal_flow.rules_store",
    "RulesEngine": "modal_flow.rules_engine",
    "QuestionNormalizer": "modal_flow.normalizer",
    "FieldSignature": "modal_flow.field_signature",
    "CandidateProfile": "modal_flow.profile_schema",
    "BaseLLMDelegate": "modal_flow.llm_delegate",
    "LLMDecision": "modal_flow.llm_delegate",
    "OpenAILLMDelegate": "modal_flow.llm_delegate_openai",
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module 'modal_flow' has no attribute '{name}'")
    module = import_module(_LAZY_IMPORTS[name])
    value = getattr(module, name)
    globals()[name] = value
    return value
