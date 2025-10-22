"""Utilities for managing document uploads inside LinkedIn Easy Apply modals."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, TYPE_CHECKING

from playwright.async_api import Locator, Page

from llm.cover_letter_generator import generate_cover_letter, save_cover_letter
from modal_flow.normalizer import QuestionNormalizer

if TYPE_CHECKING:
    from config import AppConfig


COVER_LABEL_RX = re.compile(r"(cover|soprovoditel|motivation|motiva|сопровод|мотивац)", re.I)


@dataclass
class DocumentPaths:
    """Stores filesystem paths for documents that may be uploaded."""

    resume: Optional[Path] = None
    cover_letter: Optional[Path] = None
    extra: Dict[str, Path] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.resume, str):
            self.resume = Path(self.resume)
        if isinstance(self.cover_letter, str):
            self.cover_letter = Path(self.cover_letter)
        for key, value in list(self.extra.items()):
            if isinstance(value, str):
                self.extra[key] = Path(value)


@dataclass
class DocumentUploadState:
    """Tracks which optional documents were uploaded during the modal flow."""

    cover_letter_uploaded: bool = False

    def mark_uploaded(self, doc_type: str) -> None:
        if doc_type == "cover":
            self.cover_letter_uploaded = True

    def already_uploaded(self, doc_type: str) -> bool:
        return doc_type == "cover" and self.cover_letter_uploaded

    def is_finished(self, document_paths: DocumentPaths, has_lazy_cover: bool) -> bool:
        cover_needed = document_paths.cover_letter is not None or has_lazy_cover
        return (not cover_needed) or self.cover_letter_uploaded


class CoverLetterLazyGenerator:
    """Generates cover letter only when a modal actually asks for it."""

    def __init__(
        self, job_id: int, app_config: "AppConfig", logger: logging.Logger
    ) -> None:
        self._job_id = job_id
        self._app_config = app_config
        self._logger = logger
        self._generated_path: Optional[Path] = None

    async def get_path(self) -> Optional[Path]:
        """Return an existing or lazily generated cover letter path."""

        if self._generated_path and self._generated_path.exists():
            return self._generated_path

        if not (self._app_config.llm.LLM_API_KEY and self._app_config.llm.LLM_PROVIDER):
            self._logger.warning(
                "Cannot generate cover letter lazily because LLM credentials are missing"
            )
            return None

        self._logger.info(
            "Generating cover letter lazily for job_id=%s", self._job_id
        )
        try:
            generated_path = await asyncio.to_thread(
                generate_cover_letter, self._job_id, self._app_config
            )
            saved_path = await asyncio.to_thread(
                save_cover_letter, self._job_id, generated_path, "generated_letters"
            )
            self._generated_path = Path(saved_path)
            self._logger.info(
                "Lazy cover letter generated at %s", self._generated_path
            )
            return self._generated_path
        except Exception as exc:  # pragma: no cover - best effort logging
            self._logger.error(
                "Failed to lazily generate cover letter for job_id=%s: %s",
                self._job_id,
                exc,
            )
            return None

    async def cleanup(self) -> None:
        """Remove temporary cover letter if requested by config."""

        if (
            self._generated_path
            and self._generated_path.exists()
            and self._app_config.form_data.delete_cover_letter_after_use
        ):
            try:
                self._generated_path.unlink(missing_ok=True)
                self._logger.info(
                    "Removed lazily generated cover letter: %s",
                    self._generated_path,
                )
            except Exception as exc:  # pragma: no cover
                self._logger.warning(
                    "Failed to delete temporary cover letter %s: %s",
                    self._generated_path,
                    exc,
                )


class ModalDocumentUploader:
    """Detects document upload sections and attaches files automatically."""

    def __init__(
        self,
        page: Page,
        normalizer: QuestionNormalizer,
        document_paths: DocumentPaths,
        logger: Optional[logging.Logger] = None,
        lazy_generator: Optional[CoverLetterLazyGenerator] = None,
    ) -> None:
        self._page = page
        self._normalizer = normalizer
        self._document_paths = document_paths
        self._lazy_generator = lazy_generator
        self._state = DocumentUploadState()
        self._logger = logger or logging.getLogger(__name__)

    async def handle_modal(self, modal: Locator) -> None:
        """Attempt to upload resume/cover letter if modal exposes slots."""

        if self._state.is_finished(
            self._document_paths, has_lazy_cover=self._lazy_generator is not None
        ):
            return

        upload_sections = modal.locator("div[class*='jobs-document-upload']")
        count = await upload_sections.count()

        for idx in range(count):
            section = upload_sections.nth(idx)
            await self._process_section(section)

        # Fallback: try any bare file inputs that are not inside the known wrappers.
        await self._process_loose_inputs(modal)

    async def _process_section(self, section: Locator) -> None:
        label_text = await self._extract_label_text(section)
        doc_type = self._classify_label(label_text)
        if not doc_type:
            return
        await self._maybe_upload(section, doc_type)

    async def _process_loose_inputs(self, modal: Locator) -> None:
        inputs = modal.locator("input[type='file']")
        count = await inputs.count()

        for idx in range(count):
            input_locator = inputs.nth(idx)
            label_text = await self._extract_label_text(input_locator)
            doc_type = self._classify_label(label_text)
            if not doc_type:
                continue
            await self._maybe_upload_via_input(input_locator, doc_type)

    async def _maybe_upload(self, section: Locator, doc_type: str) -> None:
        if self._state.already_uploaded(doc_type):
            return

        input_locator = section.locator("input[type='file']").first
        if not await input_locator.count():
            button = section.get_by_role("button").filter(
                has_text=re.compile("upload", re.I)
            )
            if await button.count():
                await button.first.click()
                await self._page.wait_for_timeout(200)
                input_locator = section.locator("input[type='file']").first

        if not await input_locator.count():
            return

        await self._maybe_upload_via_input(input_locator, doc_type)

    async def _maybe_upload_via_input(self, input_locator: Locator, doc_type: str) -> None:
        if self._state.already_uploaded(doc_type):
            return

        path = await self._resolve_path(doc_type)
        if not path:
            return

        await input_locator.set_input_files(str(path))
        self._logger.info("Uploaded %s from %s", doc_type, path)
        self._state.mark_uploaded(doc_type)

    async def _resolve_path(self, doc_type: str) -> Optional[Path]:
        if doc_type == "cover":
            cover_path = self._document_paths.cover_letter
            if cover_path and cover_path.exists():
                return cover_path
            if cover_path and not cover_path.exists():
                self._logger.warning(
                    "Configured cover letter path %s not found", cover_path
                )

            if self._lazy_generator:
                generated = await self._lazy_generator.get_path()
                if generated:
                    self._document_paths.cover_letter = generated
                    return generated
            return None

        # Unknown types might be handled later (extra attachments)
        extra_path = self._document_paths.extra.get(doc_type)
        return extra_path if extra_path and extra_path.exists() else None

    async def _extract_label_text(self, locator: Locator) -> str:
        # Try visible text first if it clearly mentions cover letters
        visible_text = ""
        try:
            visible_text = (await locator.inner_text()) or ""
        except Exception:
            visible_text = ""

        if visible_text:
            normalized_visible = self._normalizer.normalize_string(visible_text)
            if COVER_LABEL_RX.search(normalized_visible):
                return visible_text.strip()

        # Then check aria-label
        aria_label = await locator.get_attribute("aria-label")
        if aria_label:
            normalized_aria = self._normalizer.normalize_string(aria_label)
            if COVER_LABEL_RX.search(normalized_aria):
                return aria_label.strip()
            if aria_label.strip():
                return aria_label.strip()

        labelledby = await locator.get_attribute("aria-labelledby")
        if labelledby:
            text = await locator.evaluate(
                """(el) => {
                const ids = el.getAttribute('aria-labelledby');
                if (!ids) return '';
                return ids
                    .split(' ')
                    .map(id => el.ownerDocument.getElementById(id))
                    .filter(Boolean)
                    .map(node => node.innerText)
                    .join(' ');
            }"""
            )
            if text:
                return text.strip()

        label = locator.locator("label").first
        if await label.count():
            return (await label.inner_text()).strip()

        title_span = locator.locator(
            "xpath=.//span[contains(@class, 'jobs-document-upload__title')]"
        )
        if await title_span.count():
            return (await title_span.first.inner_text()).strip()

        if visible_text and visible_text.strip():
            return visible_text.strip()

        return ""

    def _classify_label(self, text: str) -> Optional[str]:
        normalized = self._normalizer.normalize_string(text or "")
        if not normalized:
            return None
        if COVER_LABEL_RX.search(normalized):
            return "cover"
        return None
