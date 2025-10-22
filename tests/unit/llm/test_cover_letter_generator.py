import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from docx import Document as DocReader

from llm.cover_letter_generator import generate_cover_letter, save_cover_letter
from llm.exceptions import (
    CoverLetterGenerationError,
    CoverLetterSaveError,
    LLMGenerationError,
    ResumeReadError,
    VacancyNotFoundError,
)
from llm.structured_schemas import LetterParts


@pytest.fixture
def mock_db_get_vacancy():
    """Fixture to mock database vacancy retrieval."""
    with patch("llm.cover_letter_generator.get_vacancy_by_id") as mock:
        yield mock


@pytest.fixture
def mock_read_resume():
    """Fixture to mock resume text reading."""
    with patch(
        "llm.cover_letter_generator.read_resume_text", return_value="My resume text."
    ) as mock:
        yield mock


@pytest.fixture
def mock_llm_client():
    """Fixture to mock the LLM client and its structured output method."""
    with patch("llm.cover_letter_generator.get_llm_client") as mock_get_client:
        mock_llm = MagicMock()
        mock_get_client.return_value = mock_llm
        yield mock_llm


def test_generate_cover_letter_success(
    mock_db_get_vacancy: MagicMock,
    mock_read_resume: MagicMock,
    mock_llm_client: MagicMock,
    app_config,
):
    """Test successful generation of a cover letter using the structured approach."""
    vacancy = {
        "id": "vac-123",
        "title": "Software Engineer",
        "company": "Tech Corp",
        "description": "A great job.",
    }
    mock_db_get_vacancy.return_value = vacancy

    # Mock the structured response from the LLM
    # Each paragraph must have >= 40 words according to LetterParts validation
    mock_parts = LetterParts(
        greeting="Dear Hiring Manager,",
        paragraphs=[
            " ".join(["This is paragraph one with enough words to meet the validation requirement."] * 10),
            " ".join(["This is paragraph two with enough words to meet the validation requirement."] * 10),
            " ".join(["This is paragraph three with enough words to meet the validation requirement."] * 10),
        ],
        closing="Sincerely,",
        signature="John Doe",
    )
    mock_llm_client.generate_structured_response.return_value = mock_parts

    letter = generate_cover_letter(vacancy["id"], app_config)

    assert "Dear Hiring Manager," in letter
    assert "paragraph one" in letter
    assert "Sincerely," in letter
    assert "John Doe" in letter
    mock_llm_client.generate_structured_response.assert_called_once()


def test_generate_cover_letter_validation_error_retry(
    mock_db_get_vacancy: MagicMock,
    mock_read_resume: MagicMock,
    mock_llm_client: MagicMock,
    app_config,
):
    """Test the retry mechanism on ValidationError."""
    vacancy = {"id": "vac-1", "title": "Job"}
    mock_db_get_vacancy.return_value = vacancy

    # First call raises a validation error, second call succeeds
    # Each paragraph must have >= 40 words according to LetterParts validation
    valid_parts = LetterParts(
        greeting="Hello,",
        paragraphs=[
            " ".join(["This is a valid paragraph with enough words to pass validation."] * 10),
            " ".join(["This is another valid paragraph with enough words to pass validation."] * 10),
            " ".join(["This is the third valid paragraph with enough words to pass validation."] * 10),
        ],
        closing="Regards,",
        signature="Jane",
    )
    mock_llm_client.generate_structured_response.side_effect = [
        ValidationError.from_exception_data("Validation Failed", []),
        valid_parts,
    ]

    letter = generate_cover_letter(vacancy["id"], app_config)

    assert "Hello," in letter
    assert "Regards," in letter
    assert mock_llm_client.generate_structured_response.call_count == 2


def test_generate_cover_letter_vacancy_not_found(
    mock_db_get_vacancy: MagicMock, app_config
):
    """Test that VacancyNotFoundError is raised when the vacancy is not in the DB."""
    mock_db_get_vacancy.return_value = None
    with pytest.raises(VacancyNotFoundError):
        generate_cover_letter("non-existent-id", app_config)


def test_generate_cover_letter_resume_read_error(
    mock_db_get_vacancy: MagicMock, mock_read_resume: MagicMock, app_config
):
    """Test that ResumeReadError is propagated correctly."""
    mock_db_get_vacancy.return_value = {"id": "vac-1", "title": "Job"}
    mock_read_resume.side_effect = ResumeReadError("File not found")
    with pytest.raises(ResumeReadError):
        generate_cover_letter("vac-1", app_config)


def test_generate_cover_letter_llm_error(
    mock_db_get_vacancy: MagicMock,
    mock_read_resume: MagicMock,
    mock_llm_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
    app_config,
):
    """Test that LLM errors are caught and raised as CoverLetterGenerationError."""
    vacancy = {"id": "vac-1", "title": "Job"}
    mock_db_get_vacancy.return_value = vacancy

    mock_llm_client.generate_structured_response.side_effect = LLMGenerationError(
        "API down"
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(CoverLetterGenerationError):
            generate_cover_letter(vacancy["id"], app_config)

    assert "Failed to generate cover letter" in caplog.text


def test_save_cover_letter_success(tmp_path):
    """Test that a cover letter is saved successfully."""
    output_dir = tmp_path / "letters"
    vacancy_id = 123
    content = "This is a cover letter."

    filepath = save_cover_letter(vacancy_id, content, str(output_dir))

    assert os.path.exists(filepath)
    doc = DocReader(filepath)
    combined_text = "\n".join(p.text for p in doc.paragraphs)
    assert "This is a cover letter." in combined_text
    assert filepath == str(output_dir / f"cover_letter_{vacancy_id}.docx")


def test_save_cover_letter_os_error(tmp_path):
    """
    Test that a CoverLetterSaveError is raised on OS error during file write.
    This test uses mocking to avoid platform-specific filesystem permission issues.
    """
    output_dir = tmp_path / "letters"
    output_dir.mkdir()  # Create the directory so makedirs doesn't fail

    with patch("llm.cover_letter_generator.Document") as mock_document:
        mock_doc = MagicMock()
        mock_doc.save.side_effect = PermissionError("Permission denied")
        mock_document.return_value = mock_doc

        with pytest.raises(CoverLetterSaveError):
            save_cover_letter(456, "some content", str(output_dir))
