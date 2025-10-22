import logging
from types import SimpleNamespace
from config import AppConfig
from llm.exceptions import ResumeReadError

logger = logging.getLogger(__name__)


def read_resume_text(app_config: AppConfig, path: str | None = None) -> str:
    """
    Read text from a resume file.

    Args:
        app_config (AppConfig): Application configuration object.
        path: Optional path to the resume file. If not provided, uses the path from app_config.

    Returns:
        Contents of the resume file as a string.

    Raises:
        ResumeReadError: If the file is not found or another read error occurs.
    """
    actual_path = path if path is not None else app_config.llm.RESUME_TXT_PATH
    try:
        with open(actual_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError as e:
        logger.error(f"Resume file not found at {actual_path}")
        raise ResumeReadError(
            path=str(actual_path), message=f"Resume file not found at {actual_path}"
        ) from e
    except Exception as e:
        logger.error(f"Failed to read resume file: {str(e)}")
        raise ResumeReadError(
            path=str(actual_path), message="Failed to read resume file"
        ) from e
