import logging
import re

import pytest

from llm.exceptions import ResumeReadError
from llm.resume_utils import read_resume_text


def test_read_resume_text_success(tmp_path, app_config):
    """Test successful reading of a resume file."""
    resume_content = "This is my professional experience."
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text(resume_content, encoding="utf-8")

    # Create a copy of llm_config with the new path
    llm_config_with_resume = app_config.llm.model_copy(
        update={"RESUME_TXT_PATH": str(resume_file)}
    )
    # Create a copy of app_config with the updated llm_config
    app_config_with_resume = app_config.model_copy(
        update={"llm": llm_config_with_resume}
    )

    text = read_resume_text(app_config_with_resume)
    assert text == resume_content


def test_read_resume_text_file_not_found(tmp_path, app_config, caplog):
    """Test that ResumeReadError is raised for a non-existent file."""
    non_existent_path = tmp_path / "non_existent_resume.txt"

    # Create copies of config with the new path
    llm_config_with_resume = app_config.llm.model_copy(
        update={"RESUME_TXT_PATH": str(non_existent_path)}
    )
    app_config_with_resume = app_config.model_copy(
        update={"llm": llm_config_with_resume}
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            ResumeReadError,
            match=re.escape(f"Resume file not found at {non_existent_path}"),
        ):
            read_resume_text(app_config_with_resume)

    assert "Resume file not found" in caplog.text


def test_read_resume_text_empty_file(tmp_path, app_config):
    """Test that an empty file returns an empty string without error."""
    resume_file = tmp_path / "empty_resume.txt"
    resume_file.touch()  # Create an empty file

    # Create copies of config with the new path
    llm_config_with_resume = app_config.llm.model_copy(
        update={"RESUME_TXT_PATH": str(resume_file)}
    )
    app_config_with_resume = app_config.model_copy(
        update={"llm": llm_config_with_resume}
    )

    text = read_resume_text(app_config_with_resume)
    assert text == ""


def test_read_resume_text_other_exception(tmp_path, app_config, caplog):
    """Test that other file-related exceptions are caught and re-raised."""
    # For example, a directory instead of a file
    resume_dir = tmp_path / "resume_dir"
    resume_dir.mkdir()

    # Create copies of config with the new path
    llm_config_with_resume = app_config.llm.model_copy(
        update={"RESUME_TXT_PATH": str(resume_dir)}
    )
    app_config_with_resume = app_config.model_copy(
        update={"llm": llm_config_with_resume}
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ResumeReadError, match="Failed to read resume file"):
            read_resume_text(app_config_with_resume)

    assert "Failed to read resume file" in caplog.text
