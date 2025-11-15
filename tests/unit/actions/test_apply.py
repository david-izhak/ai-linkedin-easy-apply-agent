import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from playwright.async_api import TimeoutError

from actions.apply import apply_to_job, click_easy_apply_button
from core.form_filler import JobApplicationContext, FillResult, FormFillError
from core.selectors import selectors

# Ensure project root on path for imports in patched modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))


# Shared mock for resilience executor used by click_easy_apply_button
mock_executor_instance = AsyncMock()


@pytest.fixture(autouse=True)
def mock_get_resilience_executor():
    with patch(
        "actions.apply.resilience.get_resilience_executor",
        return_value=mock_executor_instance,
    ):
        mock_executor_instance.reset_mock()
        mock_executor_instance.execute_operation = AsyncMock()
        yield


class TestClickEasyApplyButton:
    @pytest.mark.asyncio
    async def test_click_easy_apply_button_success(self):
        page = AsyncMock()
        
        # Mock locator chain methods
        mock_locator = AsyncMock()
        mock_locator.or_ = MagicMock(return_value=mock_locator)
        mock_locator.first = AsyncMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.last = AsyncMock()
        mock_locator.nth = MagicMock(return_value=AsyncMock())
        mock_locator.nth.return_value.wait_for = AsyncMock()
        mock_locator.nth.return_value.click = AsyncMock()
        mock_locator.nth.return_value.text_content = AsyncMock(return_value="Easy Apply")
        mock_locator.last.wait_for = AsyncMock()
        mock_locator.last.click = AsyncMock()
        mock_locator.last.text_content = AsyncMock(return_value="Easy Apply")
        
        page.locator = MagicMock(return_value=mock_locator)
        page.get_by_role = MagicMock(return_value=mock_locator)
        page.wait_for_selector = AsyncMock()
        
        await click_easy_apply_button(page)

        # Verify execute_operation was called (used internally by click_easy_apply_button)
        mock_executor_instance.execute_operation.assert_called()

    @pytest.mark.asyncio
    async def test_click_easy_apply_button_timeout(self):
        page = AsyncMock()
        
        # Mock locator chain methods
        mock_locator = AsyncMock()
        mock_locator.or_ = MagicMock(return_value=mock_locator)
        mock_locator.first = AsyncMock()
        mock_locator.first.wait_for = AsyncMock()
        mock_locator.count = AsyncMock(return_value=1)
        mock_locator.last = AsyncMock()
        mock_locator.nth = MagicMock(return_value=AsyncMock())
        mock_locator.nth.return_value.wait_for = AsyncMock()
        mock_locator.nth.return_value.click = AsyncMock()
        mock_locator.nth.return_value.text_content = AsyncMock(return_value="Easy Apply")
        mock_locator.last.wait_for = AsyncMock()
        mock_locator.last.click = AsyncMock()
        mock_locator.last.text_content = AsyncMock(return_value="Easy Apply")
        
        page.locator = MagicMock(return_value=mock_locator)
        page.get_by_role = MagicMock(return_value=mock_locator)
        page.wait_for_selector = AsyncMock()
        
        mock_executor_instance.execute_operation.side_effect = TimeoutError("Timeout")

        with pytest.raises(TimeoutError):
            await click_easy_apply_button(page)

        mock_executor_instance.execute_operation.assert_called()
        mock_executor_instance.execute_operation.side_effect = None  # cleanup for other tests


class TestApplyToJob:
    def _build_job_context(self, should_submit: bool) -> JobApplicationContext:
        return JobApplicationContext(
            job_id=1,
            job_url="https://linkedin.com/job/1",
            job_title="Software Engineer",
            should_submit=should_submit,
            cover_letter_path=Path("cover_letter.docx"),
            job_description="Awesome role",
        )

    @pytest.mark.asyncio
    @patch("actions.apply.click_easy_apply_button", new_callable=AsyncMock)
    async def test_apply_to_job_success_with_submit(
        self,
        mock_click_easy_apply_button: AsyncMock,
    ):
        page = AsyncMock()
        job_context = self._build_job_context(should_submit=True)
        coordinator = AsyncMock()
        coordinator.fill = AsyncMock(
            return_value=FillResult(
                completed=True,
                submitted=True,
                validation_errors=[],
                mode="modal_flow",
            )
        )

        result = await apply_to_job(page, job_context.job_url, job_context, coordinator)

        mock_click_easy_apply_button.assert_awaited_once_with(page)
        coordinator.fill.assert_awaited_once_with(page, job_context)
        assert result.submitted is True

    @pytest.mark.asyncio
    @patch("actions.apply.click_easy_apply_button", new_callable=AsyncMock)
    async def test_apply_to_job_success_without_submit(
        self,
        mock_click_easy_apply_button: AsyncMock,
    ):
        page = AsyncMock()
        job_context = self._build_job_context(should_submit=False)
        coordinator = AsyncMock()
        coordinator.fill = AsyncMock(
            return_value=FillResult(
                completed=True,
                submitted=False,
                validation_errors=[],
                mode="modal_flow",
            )
        )

        result = await apply_to_job(page, job_context.job_url, job_context, coordinator)

        mock_click_easy_apply_button.assert_awaited_once_with(page)
        coordinator.fill.assert_awaited_once_with(page, job_context)
        assert result.submitted is False

    @pytest.mark.asyncio
    @patch("actions.apply.click_easy_apply_button", new_callable=AsyncMock)
    async def test_apply_to_job_easy_apply_button_error(
        self,
        mock_click_easy_apply_button: AsyncMock,
    ):
        page = AsyncMock()
        job_context = self._build_job_context(should_submit=True)
        coordinator = AsyncMock()
        mock_click_easy_apply_button.side_effect = RuntimeError("button missing")

        with pytest.raises(RuntimeError, match="button missing"):
            await apply_to_job(page, job_context.job_url, job_context, coordinator)

        coordinator.fill.assert_not_called()

    @pytest.mark.asyncio
    @patch("actions.apply.click_easy_apply_button", new_callable=AsyncMock)
    async def test_apply_to_job_form_filling_failure(
        self,
        mock_click_easy_apply_button: AsyncMock,
    ):
        page = AsyncMock()
        job_context = self._build_job_context(should_submit=True)
        coordinator = AsyncMock()
        coordinator.fill = AsyncMock(side_effect=FormFillError("failed to fill"))

        with pytest.raises(FormFillError, match="failed to fill"):
            await apply_to_job(page, job_context.job_url, job_context, coordinator)

        mock_click_easy_apply_button.assert_awaited_once_with(page)
        coordinator.fill.assert_awaited_once_with(page, job_context)
