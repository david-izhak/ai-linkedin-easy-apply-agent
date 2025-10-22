import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from modal_flow.document_upload import (
    CoverLetterLazyGenerator,
    DocumentPaths,
    ModalDocumentUploader,
)


class DummyNormalizer:
    def normalize_string(self, value: str) -> str:
        return (value or "").lower().strip()


def test_document_paths_casts_strings(tmp_path):
    resume = tmp_path / "cv.pdf"
    resume.write_text("data")
    cover = tmp_path / "cl.pdf"
    cover.write_text("cover")

    paths = DocumentPaths(resume=str(resume), cover_letter=str(cover))

    assert isinstance(paths.resume, Path)
    assert isinstance(paths.cover_letter, Path)
    assert paths.resume == resume
    assert paths.cover_letter == cover


@pytest.mark.asyncio
async def test_modal_document_uploader_resolves_cover_via_lazy_generator(tmp_path):
    cover = tmp_path / "generated.txt"
    cover.write_text("hello")

    class DummyLazy:
        def __init__(self):
            self.calls = 0

        async def get_path(self):
            self.calls += 1
            return cover

    document_paths = DocumentPaths()
    lazy = DummyLazy()
    uploader = ModalDocumentUploader(
        page=AsyncMock(),
        normalizer=DummyNormalizer(),
        document_paths=document_paths,
        lazy_generator=lazy,
    )

    resolved = await uploader._resolve_path("cover")

    assert resolved == cover
    assert document_paths.cover_letter == cover
    assert lazy.calls == 1


def test_modal_document_uploader_ignores_resume_labels():
    uploader = ModalDocumentUploader(
        page=AsyncMock(),
        normalizer=DummyNormalizer(),
        document_paths=DocumentPaths(),
    )

    assert uploader._classify_label("Resume") is None
    assert uploader._classify_label("Загрузить резюме") is None


@pytest.mark.asyncio
async def test_extract_label_prefers_visible_cover_text():
    locator = AsyncMock()
    locator.inner_text = AsyncMock(return_value="Upload cover letter")
    locator.get_attribute = AsyncMock(return_value="Upload resume button")
    nested = AsyncMock()
    nested.count = AsyncMock(return_value=0)
    locator.locator.return_value = nested

    uploader = ModalDocumentUploader(
        page=AsyncMock(),
        normalizer=DummyNormalizer(),
        document_paths=DocumentPaths(),
    )

    label = await uploader._extract_label_text(locator)
    assert "cover" in label.lower()


@pytest.mark.asyncio
async def test_cover_letter_lazy_generator_skips_without_credentials(app_config):
    config_no_llm = app_config.model_copy(
        update={
            "llm": app_config.llm.model_copy(
                update={"LLM_API_KEY": "", "LLM_PROVIDER": ""}
            )
        }
    )

    generator = CoverLetterLazyGenerator(
        job_id=1,
        app_config=config_no_llm,
        logger=logging.getLogger(__name__),
    )

    result = await generator.get_path()
    assert result is None


@pytest.mark.asyncio
async def test_cover_letter_lazy_generator_generates_and_cleans(
    app_config, tmp_path, monkeypatch
):
    raw_file = tmp_path / "raw.txt"
    saved_file = tmp_path / "saved.docx"

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    def fake_generate(job_id, config):
        raw_file.write_text("draft")
        return str(raw_file)

    def fake_save(job_id, generated_path, output_dir):
        saved_file.write_text(Path(generated_path).read_text())
        return str(saved_file)

    monkeypatch.setattr("modal_flow.document_upload.asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(
        "modal_flow.document_upload.generate_cover_letter", fake_generate
    )
    monkeypatch.setattr(
        "modal_flow.document_upload.save_cover_letter", fake_save
    )

    app_config.form_data.delete_cover_letter_after_use = True

    generator = CoverLetterLazyGenerator(
        job_id=42,
        app_config=app_config,
        logger=logging.getLogger(__name__),
    )

    path = await generator.get_path()

    assert path == saved_file
    assert path.exists()

    await generator.cleanup()

    assert not path.exists()
