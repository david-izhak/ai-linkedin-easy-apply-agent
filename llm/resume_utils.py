import json
import logging
from pathlib import Path
from typing import Any

from pydantic import HttpUrl, ValidationError

from config import AppConfig
from llm.exceptions import ResumeReadError
from modal_flow.profile_store import ProfileStore

logger = logging.getLogger(__name__)


def _resolve_profile_path(app_config: AppConfig, path: str | None = None) -> Path:
    if path:
        return Path(path)
    return Path(app_config.modal_flow.profile_path)


def _make_json_serializable(obj: Any) -> Any:
    """
    Recursively convert Pydantic types (like HttpUrl) to JSON-serializable types.
    
    Args:
        obj: Object to convert (can be dict, list, or primitive)
        
    Returns:
        JSON-serializable version of the object
    """
    if isinstance(obj, HttpUrl):
        return str(obj)
    if isinstance(obj, dict):
        return {key: _make_json_serializable(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    return obj


def read_resume_text(app_config: AppConfig, path: str | None = None) -> str:
    """
    Load candidate profile JSON and return a serialized summary for LLM prompts.

    Args:
        app_config (AppConfig): Application configuration object.
        path: Optional path to the candidate profile. Uses modal_flow.profile_path by default.

    Returns:
        A JSON-formatted string with candidate data.

    Raises:
        ResumeReadError: If the profile cannot be read or validated.
    """
    profile_path = _resolve_profile_path(app_config, path)

    try:
        profile = ProfileStore(profile_path).load()
        payload = profile.to_json_summary()
        # Convert Pydantic types (like HttpUrl) to JSON-serializable types
        serializable_payload = _make_json_serializable(payload)
        return json.dumps(serializable_payload, ensure_ascii=False, indent=2)
    except FileNotFoundError as exc:
        logger.error("Candidate profile not found at %s", profile_path)
        raise ResumeReadError(
            path=str(profile_path),
            message=f"Candidate profile not found at {profile_path}",
        ) from exc
    except json.JSONDecodeError as exc:
        logger.error("Invalid candidate profile at %s: %s", profile_path, exc)
        raise ResumeReadError(
            path=str(profile_path),
            message=f"Invalid candidate profile at {profile_path}",
        ) from exc
    except ValidationError as exc:
        logger.error("Invalid candidate profile at %s: %s", profile_path, exc)
        raise ResumeReadError(
            path=str(profile_path),
            message=f"Invalid candidate profile at {profile_path}",
        ) from exc
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("Failed to load candidate profile from %s: %s", profile_path, exc)
        raise ResumeReadError(
            path=str(profile_path), message="Failed to load candidate profile"
        ) from exc
