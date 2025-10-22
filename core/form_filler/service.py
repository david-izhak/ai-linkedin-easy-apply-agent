import logging
from typing import Optional

from playwright.async_api import Page

from config import AppConfig
from modal_flow.document_upload import (
    CoverLetterLazyGenerator,
    DocumentPaths,
)

from .modal_flow_impl import ModalFlowFormFiller
from .modal_flow_resources import ModalFlowResources
from .models import FillResult, JobApplicationContext


class FormFillCoordinator:
    """Coordinates form filling using the modal flow implementation."""

    def __init__(
        self,
        app_config: AppConfig,
        resources: ModalFlowResources,
        logger: Optional[logging.Logger] = None,
    ):
        self._app_config = app_config
        self._logger = logger or logging.getLogger(__name__)

        self._modal_flow_filler = ModalFlowFormFiller(
            resources=resources,
            max_steps=app_config.modal_flow.max_steps,
            logger=self._logger,
        )

    async def fill(
        self,
        page: Page,
        job_context: JobApplicationContext,
    ) -> FillResult:
        """Fill using the modal flow form filler."""
        document_paths = DocumentPaths(
            resume=self._app_config.form_data.cv_path,
            cover_letter=job_context.cover_letter_path
            or self._app_config.form_data.cover_letter_path,
        )

        lazy_generator: Optional[CoverLetterLazyGenerator] = None
        if (
            not document_paths.cover_letter
            and self._app_config.llm.LLM_API_KEY
            and self._app_config.llm.LLM_PROVIDER
        ):
            lazy_generator = CoverLetterLazyGenerator(
                job_id=job_context.job_id,
                app_config=self._app_config,
                logger=self._logger,
            )

        result: FillResult = await self._modal_flow_filler.fill(
            page,
            self._app_config,
            job_context,
            document_paths=document_paths,
            lazy_generator=lazy_generator,
        )
        self._logger.debug("Modal flow result: %s", result)
        return result
