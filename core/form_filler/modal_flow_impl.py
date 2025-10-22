import logging
from typing import Any, Optional

from playwright.async_api import Page

from config import AppConfig
from modal_flow.document_upload import (
    CoverLetterLazyGenerator,
    DocumentPaths,
)
from modal_flow.modal_flow import ModalFlowRunner, ModalFlowRunResult
from .base import AbstractFormFiller
from .modal_flow_resources import ModalFlowResources
from .models import FillResult, JobApplicationContext, FormFillError


class ModalFlowFormFiller(AbstractFormFiller):
    """Form filler that delegates to ModalFlowRunner with rules/LLM support."""

    def __init__(
        self,
        resources: ModalFlowResources,
        max_steps: int = 8,
        logger: Optional[logging.Logger] = None,
    ):
        self._resources = resources
        self._max_steps = max_steps
        self._logger = logger or logging.getLogger(__name__)

    async def fill(
        self,
        page: Page,
        app_config: AppConfig,
        job_context: JobApplicationContext,
        *,
        document_paths: DocumentPaths,
        lazy_generator: Optional[CoverLetterLazyGenerator] = None,
    ) -> FillResult:
        self._logger.debug(
            "Modal flow filler started for job_id=%s", job_context.job_id
        )

        try:
            runner = ModalFlowRunner(
                page=page,
                profile=self._resources.profile,
                rule_store=self._resources.rule_store,
                normalizer=self._resources.normalizer,
                llm_delegate=self._resources.llm_delegate,
                learning_config=self._resources.learning_config,
                logger=self._logger,
            )

            outcome: Any = await runner.run(
                max_steps=self._max_steps,
                should_submit=job_context.should_submit,
                job_context=job_context.to_job_payload(),
                document_paths=document_paths,
                lazy_generator=lazy_generator,
            )

            if not isinstance(outcome, ModalFlowRunResult):
                raise FormFillError(
                    "Modal flow runner returned unexpected result type."
                )

            if not outcome.completed:
                raise FormFillError(
                    "Modal flow runner did not complete successfully.",
                    validation_errors=outcome.validation_errors,
                )

            return FillResult(
                completed=outcome.completed,
                submitted=outcome.submitted,
                validation_errors=outcome.validation_errors,
                mode="modal_flow",
            )

        except FormFillError:
            raise
        except Exception as exc:
            self._logger.error("Modal flow filler failed: %s", exc, exc_info=True)
            raise FormFillError(str(exc))
        finally:
            if lazy_generator:
                await lazy_generator.cleanup()
