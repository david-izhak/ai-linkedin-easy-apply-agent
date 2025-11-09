import os
import logging
from types import SimpleNamespace

from docx import Document
from pydantic import ValidationError

from config import AppConfig # Import AppConfig
from core.database import get_vacancy_by_id

from llm.client_factory import get_llm_client
from llm.exceptions import (
    VacancyNotFoundError,
    ResumeReadError,
    LLMGenerationError,
    CoverLetterGenerationError,
    CoverLetterSaveError,
)
from llm.prompts import COVER_LETTER_PROMPT_STRUCTURED
from llm.resume_utils import read_resume_text
from llm.structured_schemas import LetterParts, join_parts

logger = logging.getLogger(__name__)

# Local settings for tests to patch: llm.cover_letter_generator._test_settings.GENERATED_LETTERS_DIR
_test_settings = SimpleNamespace(GENERATED_LETTERS_DIR="generated_letters")

# Common placeholder for missing vacancy fields
NOT_SPECIFIED = "not specified"


def generate_cover_letter(
    job_id: int, app_config: AppConfig, include_ps: bool = False, include_links: bool = False
) -> str:
    """
    Generates a cover letter for a given job ID using a structured LLM approach.

    Args:
        job_id (int): Job ID
        app_config (AppConfig): Application configuration object
        include_ps (bool): Flag to include a P.S. in the letter.
        include_links (bool): Flag to include links in the letter.

    Returns:
        str: Generated cover letter
    """
    resume_path = app_config.llm.RESUME_TXT_PATH

    try:
        # We receive information about a vacancy from the database
        job = get_vacancy_by_id(job_id, app_config.session.db_conn)

        if not job:
            logger.error(f"Job with ID {job_id} not found in database")
            raise VacancyNotFoundError(vacancy_id=job_id)

        # Extract vacancy data
        inputs = {
            "job_title": job.get("title", NOT_SPECIFIED),
            "company_name": job.get("company", NOT_SPECIFIED),
            "description": job.get("description", NOT_SPECIFIED),
            "location": job.get("location", NOT_SPECIFIED),
            "company_description": job.get("company_description", NOT_SPECIFIED),
            "employment_type": job.get("employment_type", NOT_SPECIFIED),
            "company_overview": job.get("company_overview", NOT_SPECIFIED),
            "company_website": job.get("company_website", NOT_SPECIFIED),
            "company_industry": job.get("company_industry", NOT_SPECIFIED),
            "company_size": job.get("company_size", NOT_SPECIFIED),
            "resume_text": read_resume_text(app_config),
            # Add flags to the inputs dictionary to be used in the prompt template
            "include_ps": str(include_ps).lower(),
            "include_links": str(include_links).lower(),
        }

        # Obtaining an instance of the LLM client
        llm = get_llm_client(app_config.llm)

        # Prepare messages
        # The flags are now part of the inputs, so we can format directly.
        prompt = COVER_LETTER_PROMPT_STRUCTURED.format(**inputs)
        system_message = (
            "Output only via structured fields. "
            "No commentary or explanations outside the fields."
        )

        try:
            # Generate structured response
            parts: LetterParts = llm.generate_structured_response(
                prompt=prompt,
                schema=LetterParts,
                system_message=system_message,
            )
        except (LLMGenerationError, ValidationError) as e:
            # If the first attempt fails (either due to LLM error or validation),
            # we make one "soft" retry by providing feedback to the model.
            logger.warning(
                f"Initial cover letter generation failed: {str(e)}. Retrying with feedback..."
            )
            feedback = f"\n\nVALIDATION FEEDBACK:\n- {e}\n- Re-emit strictly via structured fields, plain text only (no markdown)."
            
            # The `generate_structured_response` in LLMClient does not support raw message lists,
            # so we append the feedback to the original prompt for the retry.
            retry_prompt = prompt + feedback
            
            parts = llm.generate_structured_response(
                prompt=retry_prompt,
                schema=LetterParts,
                system_message=system_message,
            )

        cover_letter = join_parts(parts)

        logger.info(f"A cover letter for the vacancy has been generated {job_id}")
        return cover_letter

    except (LLMGenerationError, ValidationError) as e:
        logger.error("Failed to generate cover letter even after retry.")
        raise CoverLetterGenerationError(
            vacancy_id=job_id, resume_path=resume_path
        ) from e
    except (ResumeReadError, VacancyNotFoundError):
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error during cover letter generation for vacancy {job_id}: {str(e)}"
        )
        raise CoverLetterGenerationError(
            vacancy_id=job_id, resume_path=resume_path
        ) from e


def save_cover_letter(
    vacancy_id: int, cover_letter_text: str, output_dir: str | None = None
) -> str:
    """
    Save generated cover letter to a file.

    Args:
        vacancy_id: Vacancy ID
        cover_letter_text: Cover letter content
        output_dir: Directory to save files (uses _test_settings.GENERATED_LETTERS_DIR if None)

    Returns:
        str: Path to the saved file
    """
    # Resolve output directory (allow tests to patch _test_settings.GENERATED_LETTERS_DIR)
    output_dir = output_dir or _test_settings.GENERATED_LETTERS_DIR

    # Ensure directory exists
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create directory for cover letter")
        raise CoverLetterSaveError(
            vacancy_id=vacancy_id,
            cover_letter_text=cover_letter_text,
            output_dir=str(output_dir),
        ) from e

    # Write file
    try:
        filename = f"cover_letter_{vacancy_id}.docx"
        filepath = os.path.join(output_dir, filename)

        document = Document()
        normalized_text = (cover_letter_text or "").replace("\r\n", "\n")
        paragraphs = [
            paragraph.strip()
            for paragraph in normalized_text.split("\n\n")
            if paragraph.strip()
        ]

        if not paragraphs:
            paragraphs = [cover_letter_text.strip() or ""]

        for paragraph in paragraphs:
            document.add_paragraph(paragraph)

        document.save(filepath)

        logger.info(f"Cover letter saved to {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Failed to save cover letter: {str(e)}")
        raise CoverLetterSaveError(
            vacancy_id=vacancy_id,
            cover_letter_text=cover_letter_text,
            output_dir=str(output_dir),
        ) from e
