import json
import logging
import re

import pytest
from pydantic import HttpUrl

from llm.exceptions import ResumeReadError
from llm.resume_utils import read_resume_text, _make_json_serializable


def _app_config_with_profile(app_config, profile_path):
    modal_flow_with_profile = app_config.modal_flow.model_copy(
        update={"profile_path": profile_path}
    )
    return app_config.model_copy(update={"modal_flow": modal_flow_with_profile})


def test_read_resume_text_success(tmp_path, app_config):
    """Тест успешной загрузки профиля кандидата."""
    profile_content = {"full_name": "Test Candidate", "skills": ["python", "sql"]}
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_content), encoding="utf-8")

    app_config_with_profile = _app_config_with_profile(app_config, str(profile_file))

    text = read_resume_text(app_config_with_profile)
    data = json.loads(text)
    assert data["full_name"] == "Test Candidate"
    assert data["skills"] == ["python", "sql"]


def test_read_resume_text_file_not_found(tmp_path, app_config, caplog):
    """Тест отсутствующего файла профиля."""
    missing_profile = tmp_path / "missing_profile.json"
    app_config_with_profile = _app_config_with_profile(app_config, str(missing_profile))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            ResumeReadError,
            match=re.escape(f"Candidate profile not found at {missing_profile}"),
        ):
            read_resume_text(app_config_with_profile)

    assert "Candidate profile not found" in caplog.text


def test_read_resume_text_invalid_json(tmp_path, app_config, caplog):
    """Тест невалидного JSON профиля."""
    profile_file = tmp_path / "profile.json"
    profile_file.write_text("{invalid json", encoding="utf-8")

    app_config_with_profile = _app_config_with_profile(app_config, str(profile_file))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            ResumeReadError,
            match=re.escape(f"Invalid candidate profile at {profile_file}"),
        ):
            read_resume_text(app_config_with_profile)

    assert "Invalid candidate profile" in caplog.text


def test_read_resume_text_other_exception(tmp_path, app_config, caplog):
    """Тест прочих ошибок чтения профиля."""
    profile_dir = tmp_path / "profile_dir"
    profile_dir.mkdir()

    app_config_with_profile = _app_config_with_profile(app_config, str(profile_dir))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(
            ResumeReadError, match="Failed to load candidate profile"
        ):
            read_resume_text(app_config_with_profile)

    assert "Failed to load candidate profile" in caplog.text


def test_read_resume_text_with_httpurl(tmp_path, app_config):
    """Тест сериализации профиля с HttpUrl полями (links)."""
    profile_content = {
        "full_name": "Test Candidate",
        "links": {
            "github": "https://github.com/test",
            "linkedin": "https://www.linkedin.com/in/test",
            "website": "https://example.com"
        },
        "skills": ["python", "sql"]
    }
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_content), encoding="utf-8")

    app_config_with_profile = _app_config_with_profile(app_config, str(profile_file))

    # Should not raise an error
    text = read_resume_text(app_config_with_profile)
    data = json.loads(text)
    
    # Verify that HttpUrl fields are converted to strings
    assert data["full_name"] == "Test Candidate"
    assert data["skills"] == ["python", "sql"]
    assert isinstance(data["links"]["github"], str)
    assert isinstance(data["links"]["linkedin"], str)
    assert isinstance(data["links"]["website"], str)
    assert data["links"]["github"] == "https://github.com/test"
    assert data["links"]["linkedin"] == "https://www.linkedin.com/in/test"
    assert data["links"]["website"] == "https://example.com"


def test_read_resume_text_with_nested_httpurl(tmp_path, app_config):
    """Тест сериализации профиля с вложенными структурами, содержащими HttpUrl."""
    profile_content = {
        "full_name": "Test Candidate",
        "links": {
            "github": "https://github.com/test",
            "linkedin": "https://www.linkedin.com/in/test"
        },
        "contact": {
            "website": "https://example.com",
            "portfolio": "https://portfolio.example.com"
        }
    }
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps(profile_content), encoding="utf-8")

    app_config_with_profile = _app_config_with_profile(app_config, str(profile_file))

    text = read_resume_text(app_config_with_profile)
    data = json.loads(text)
    
    # Verify nested HttpUrl fields are converted to strings
    assert isinstance(data["links"]["github"], str)
    assert isinstance(data["links"]["linkedin"], str)
    assert isinstance(data["contact"]["website"], str)
    assert isinstance(data["contact"]["portfolio"], str)


def test_make_json_serializable_with_httpurl():
    """Тест функции _make_json_serializable с реальными HttpUrl объектами."""
    # Create a dict with HttpUrl objects (as Pydantic would return)
    http_url_obj = HttpUrl("https://github.com/test")
    payload = {
        "name": "Test",
        "links": {
            "github": http_url_obj,
            "linkedin": HttpUrl("https://www.linkedin.com/in/test")
        },
        "skills": ["python", "sql"],
        "nested": {
            "website": HttpUrl("https://example.com")
        }
    }
    
    # Convert to JSON-serializable
    result = _make_json_serializable(payload)
    
    # Verify HttpUrl objects are converted to strings
    assert isinstance(result["links"]["github"], str)
    assert isinstance(result["links"]["linkedin"], str)
    assert isinstance(result["nested"]["website"], str)
    assert result["links"]["github"] == "https://github.com/test"
    assert result["links"]["linkedin"] == "https://www.linkedin.com/in/test"
    # HttpUrl may add trailing slash, so check that it starts with the expected URL
    assert result["nested"]["website"].startswith("https://example.com")
    
    # Verify other types are preserved
    assert result["name"] == "Test"
    assert result["skills"] == ["python", "sql"]
    
    # Verify it can be serialized to JSON
    json_str = json.dumps(result)
    assert "https://github.com/test" in json_str


def test_make_json_serializable_with_list_of_httpurl():
    """Тест функции _make_json_serializable со списком HttpUrl."""
    payload = {
        "urls": [
            HttpUrl("https://github.com/test"),
            HttpUrl("https://example.com"),
            "regular_string"
        ]
    }
    
    result = _make_json_serializable(payload)
    
    assert isinstance(result["urls"][0], str)
    assert isinstance(result["urls"][1], str)
    assert isinstance(result["urls"][2], str)
    assert result["urls"][0] == "https://github.com/test"
    # HttpUrl may add trailing slash, so check that it starts with the expected URL
    assert result["urls"][1].startswith("https://example.com")
    assert result["urls"][2] == "regular_string"
    
    # Verify it can be serialized to JSON
    json_str = json.dumps(result)
    assert "https://github.com/test" in json_str
