import pytest
from unittest.mock import AsyncMock, MagicMock

from modal_flow.modal_flow import ModalFlowRunner
from modal_flow.learning_config import LearningConfig
from modal_flow.normalizer import QuestionNormalizer
from modal_flow.profile_schema import CandidateProfile


def _build_runner():
    return ModalFlowRunner(
        page=AsyncMock(),
        profile=CandidateProfile(),
        rule_store=MagicMock(),
        normalizer=QuestionNormalizer(),
        llm_delegate=None,
        learning_config=LearningConfig(),
        logger=None,
    )


@pytest.mark.asyncio
async def test_compose_checkbox_question_with_legend_and_label():
    runner = _build_runner()
    checkbox = AsyncMock()
    checkbox.evaluate.side_effect = ["Legend Text", "Label Text"]

    question = await runner._compose_checkbox_question(checkbox)

    assert question == "legend: Legend Text. label: Label Text"


@pytest.mark.asyncio
async def test_compose_checkbox_question_with_label_fallback():
    runner = _build_runner()
    checkbox = AsyncMock()
    checkbox.evaluate.side_effect = ["Legend Text", ""]
    runner._label_for = AsyncMock(return_value="Fallback Label")  # type: ignore[attr-defined]

    question = await runner._compose_checkbox_question(checkbox)

    assert question == "legend: Legend Text. label: Fallback Label"


@pytest.mark.asyncio
async def test_compose_checkbox_question_without_any_text():
    runner = _build_runner()
    checkbox = AsyncMock()
    checkbox.evaluate.side_effect = ["", ""]
    runner._label_for = AsyncMock(return_value="")  # type: ignore[attr-defined]

    question = await runner._compose_checkbox_question(checkbox)

    assert question == ""

