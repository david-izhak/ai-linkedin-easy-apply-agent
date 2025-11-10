import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import (
    ModalFlowConfig,
    ModalFlowLearningSettings,
    LLMSettings,
)
from core.form_filler import (
    FormFillCoordinator,
    ModalFlowResources,
    JobApplicationContext,
    FillResult,
    FormFillError,
)
from core.form_filler.modal_flow_impl import ModalFlowFormFiller


def _build_modal_flow_config() -> ModalFlowConfig:
    learning = ModalFlowLearningSettings()
    return ModalFlowConfig(
        profile_path=Path("config/profile_example.json"),
        rules_path=Path("config/rules.yaml"),
        normalizer_rules_path=Path("config/normalizer_rules.yaml"),
        llm_delegate_enabled=False,
        learning=learning,
    )


def _build_llm_settings() -> LLMSettings:
    return LLMSettings(LLM_API_KEY="dummy-key", LLM_BASE_URL="https://example.com")


def _build_form_data():
    return SimpleNamespace(
        cv_path=Path("test_cv.pdf"),
        cover_letter_path=None,
        delete_cover_letter_after_use=False,
    )


@pytest.mark.asyncio
async def test_coordinator_uses_modal_flow(monkeypatch):
    modal_config = _build_modal_flow_config()
    llm_config = _build_llm_settings()

    dummy_app_config = SimpleNamespace(
        modal_flow=modal_config,
        llm=llm_config,
        form_data=_build_form_data(),
    )

    resources = ModalFlowResources(
        modal_flow_config=modal_config,
        llm_config=llm_config,
        logger=logging.getLogger("modal-test"),
    )
    coordinator = FormFillCoordinator(
        app_config=dummy_app_config,
        resources=resources,
        logger=logging.getLogger("modal-test"),
    )

    async def successful_modal_fill(
        self,
        page,
        app_config,
        job_context,
        *,
        document_paths,
        lazy_generator=None,
    ):
        return FillResult(
            completed=True,
            submitted=False,
            validation_errors=[],
            mode="modal_flow",
        )

    monkeypatch.setattr(ModalFlowFormFiller, "fill", successful_modal_fill)

    page_mock = MagicMock()
    job_context = JobApplicationContext(
        job_id=1,
        job_url="https://example.com/job",
        job_title="Test Job",
        should_submit=False,
    )

    result = await coordinator.fill(page_mock, job_context)

    assert result.mode == "modal_flow"
    assert result.completed is True


@pytest.mark.asyncio
async def test_coordinator_propagates_modal_flow_errors(monkeypatch):
    modal_config = _build_modal_flow_config()
    llm_config = _build_llm_settings()

    dummy_app_config = SimpleNamespace(
        modal_flow=modal_config,
        llm=llm_config,
        form_data=_build_form_data(),
    )

    resources = ModalFlowResources(
        modal_flow_config=modal_config,
        llm_config=llm_config,
        logger=logging.getLogger("modal-test"),
    )
    coordinator = FormFillCoordinator(
        app_config=dummy_app_config,
        resources=resources,
        logger=logging.getLogger("modal-test"),
    )

    async def failing_modal_fill(
        self,
        page,
        app_config,
        job_context,
        *,
        document_paths,
        lazy_generator=None,
    ):
        raise FormFillError("modal failed", validation_errors=["field error"])

    monkeypatch.setattr(ModalFlowFormFiller, "fill", failing_modal_fill)

    page_mock = MagicMock()
    job_context = JobApplicationContext(
        job_id=1,
        job_url="https://example.com/job",
        job_title="Test Job",
        should_submit=False,
    )

    with pytest.raises(FormFillError) as exc_info:
        await coordinator.fill(page_mock, job_context)

    assert "modal failed" in str(exc_info.value)


def test_modal_flow_resources_loading():
    modal_config = _build_modal_flow_config()
    llm_config = _build_llm_settings()

    resources = ModalFlowResources(
        modal_flow_config=modal_config,
        llm_config=llm_config,
        logger=logging.getLogger("modal-test"),
    )

    profile = resources.profile
    rule_store = resources.rule_store
    normalizer = resources.normalizer
    learning_config = resources.learning_config

    assert profile.full_name == "David Izhak"
    assert rule_store is resources.rule_store  # cached
    assert normalizer is resources.normalizer  # cached
    assert learning_config.confidence_threshold == pytest.approx(
        modal_config.learning.confidence_threshold
    )
