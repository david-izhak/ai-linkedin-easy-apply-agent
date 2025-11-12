import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from modal_flow.modal_flow import ModalFlowRunner


class FakeLocator:
    def __init__(self, elements):
        self._elements = elements

    async def count(self):
        return len(self._elements)

    def nth(self, index):
        return self._elements[index]

    def and_(self, other):
        return self

    def locator(self, *args, **kwargs):
        return self


@pytest.fixture
def runner():
    runner = object.__new__(ModalFlowRunner)
    runner.logger = MagicMock(spec=logging.Logger)
    runner.rules_engine = MagicMock()
    runner.rules_engine.decide = AsyncMock()
    runner.normalizer = MagicMock()
    runner.page = AsyncMock()
    runner._compose_checkbox_question = AsyncMock(return_value="checkbox question")
    runner._label_for = AsyncMock(return_value="question")
    runner._document_uploader = None
    runner.normalizer.normalize_string = MagicMock(side_effect=lambda x: x.strip())
    return runner


def test_extract_progress_percentage_from_text():
    runner = object.__new__(ModalFlowRunner)
    assert runner._extract_progress_percentage_from_text("Apply\n11%\nStep") == 11
    assert runner._extract_progress_percentage_from_text("No percentage here") is None
    assert runner._extract_progress_percentage_from_text("Progress 150%") is None


@pytest.mark.asyncio
async def test_handle_checkboxes_skips_when_same_dialog(runner):
    checkbox = AsyncMock()
    checkbox.is_checked = AsyncMock(return_value=True)

    boxes = MagicMock()
    boxes.count = AsyncMock(return_value=1)
    boxes.nth = MagicMock(return_value=checkbox)

    modal = MagicMock()
    modal.get_by_role = MagicMock(return_value=boxes)

    await runner._handle_checkboxes(modal, is_same_dialog=True)

    assert runner.rules_engine.decide.await_count == 0
    checkbox.is_checked.assert_awaited()


@pytest.mark.asyncio
async def test_handle_textboxes_skips_when_same_dialog(runner):
    textbox = AsyncMock()
    textbox.input_value = AsyncMock(return_value="already filled")
    textbox.inner_text = AsyncMock(return_value="already filled")
    textbox.fill = AsyncMock()
    textbox.get_attribute = AsyncMock(return_value="")

    textboxes_locator = FakeLocator([textbox])

    modal = MagicMock()
    modal.get_by_role = MagicMock(return_value=textboxes_locator)
    modal.locator = MagicMock(return_value=FakeLocator([]))

    await runner._handle_textboxes(modal, is_same_dialog=True)

    assert runner.rules_engine.decide.await_count == 0
    assert textbox.fill.await_count == 0
    textbox.input_value.assert_awaited()

