import logging
from unittest.mock import MagicMock
from dataclasses import dataclass, field

import pytest

from llm.exceptions import ResumeReadError, VacancyNotFoundError
from llm.vacancy_filter import is_vacancy_suitable


@pytest.fixture
def mock_db_get_vacancy(monkeypatch):
    """Fixture to mock database get_vacancy_by_id function."""
    mock_get = MagicMock()
    monkeypatch.setattr("llm.vacancy_filter.get_vacancy_by_id", mock_get)
    return mock_get


@pytest.fixture
def mock_db_connection(monkeypatch):
    """Fixture to mock database get_db_connection."""
    mock_conn = MagicMock()
    # To use the connection in a 'with' statement, we need to mock '__enter__' and '__exit__'.
    mock_conn.__enter__.return_value = "test_db_connection_string"
    mock_conn.__exit__.return_value = None
    monkeypatch.setattr("llm.vacancy_filter.get_db_connection", lambda x: mock_conn)
    return mock_conn


@pytest.fixture
def mock_read_resume(monkeypatch):
    """Fixture to mock read_resume_text function."""
    mock_read = MagicMock(return_value="My resume text.")
    monkeypatch.setattr("llm.vacancy_filter.read_resume_text", mock_read)
    return mock_read


@pytest.fixture
def mock_calculate_skill_match(monkeypatch):
    """Fixture to mock calculate_skill_match function."""
    mock_calculate = MagicMock(return_value=(80, "Good match", "success"))
    monkeypatch.setattr("llm.vacancy_filter.calculate_skill_match", mock_calculate)
    return mock_calculate


@pytest.fixture
def mock_db_save_skill_match(monkeypatch):
    """Fixture to mock database save_skill_match_data function."""
    mock_save = MagicMock()
    monkeypatch.setattr("llm.vacancy_filter.save_skill_match_data", mock_save)
    return mock_save


@pytest.mark.asyncio
async def test_is_vacancy_suitable_not_found(
    mock_db_get_vacancy, caplog, app_config, mock_db_connection
):
    """Test that VacancyNotFoundError is raised when vacancy is not in DB."""
    mock_db_get_vacancy.return_value = None
    vacancy_id = "non-existent-id"

    with caplog.at_level(logging.WARNING):
        with pytest.raises(VacancyNotFoundError):
            await is_vacancy_suitable(vacancy_id, app_config)

    mock_db_get_vacancy.assert_called_once_with(
        vacancy_id, "test_db_connection_string"
    )
    assert any(
        record.vacancy_id == vacancy_id and record.result_status == "vacancy_not_found"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_is_vacancy_suitable_no_description(
    mock_db_get_vacancy, caplog, app_config, mock_db_connection
):
    """Test that it returns False if the vacancy has no description."""
    vacancy = {"id": "vac-1", "description": ""}
    mock_db_get_vacancy.return_value = vacancy

    with caplog.at_level(logging.INFO):
        result, reason = await is_vacancy_suitable(vacancy["id"], app_config)

    mock_db_get_vacancy.assert_called_once_with(
        vacancy["id"], "test_db_connection_string"
    )
    assert result is False
    assert reason == "No description found"
    assert any(
        record.vacancy_id == vacancy["id"] and record.result_status == "no_description"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_is_vacancy_suitable_resume_read_error(
    mock_db_get_vacancy, mock_read_resume, caplog, app_config, mock_db_connection
):
    """Test that ResumeReadError is propagated."""
    vacancy = {"id": "vac-1", "description": "A job."}
    mock_db_get_vacancy.return_value = vacancy
    mock_read_resume.side_effect = ResumeReadError("File not found")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ResumeReadError):
            await is_vacancy_suitable(vacancy["id"], app_config)

    mock_db_get_vacancy.assert_called_once_with(
        vacancy["id"], "test_db_connection_string"
    )
    assert any(
        record.vacancy_id == vacancy["id"]
        and record.result_status == "resume_read_error"
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "match_percentage, threshold, expected_result",
    [
        (69, 70, False),
        (70, 70, True),
        (71, 70, True),
        (0, 0, True),
        (100, 100, True),
    ],
)
@pytest.mark.asyncio
async def test_is_vacancy_suitable_threshold_logic(
    mock_db_get_vacancy,
    mock_db_save_skill_match,
    mock_read_resume,
    mock_calculate_skill_match,
    caplog,
    match_percentage,
    threshold,
    expected_result,
    app_config,
    mock_db_connection,
):
    """Test the comparison logic against the suitability threshold."""
    # Create a copy of llm_config with the new threshold
    llm_config_with_threshold = app_config.llm.model_copy(
        update={"LLM_THRESHOLD_PERCENTAGE": threshold}
    )
    # Create a copy of app_config with the updated llm_config
    app_config_with_threshold = app_config.model_copy(
        update={"llm": llm_config_with_threshold}
    )

    vacancy = {"id": "vac-1", "description": "A job description."}
    mock_db_get_vacancy.return_value = vacancy
    mock_calculate_skill_match.return_value = (
        match_percentage,
        "analysis",
        "success",
    )

    with caplog.at_level(logging.INFO):
        result, _ = await is_vacancy_suitable(vacancy["id"], app_config_with_threshold)

    assert result is expected_result
    mock_db_get_vacancy.assert_called_once_with(
        vacancy["id"], "test_db_connection_string"
    )
    mock_db_save_skill_match.assert_called_once_with(
        vacancy["id"], match_percentage, "analysis", "test_db_connection_string"
    )

    final_log = next(
        (r for r in caplog.records if r.message == "Vacancy suitability assessed"), None
    )
    assert final_log is not None
    assert final_log.is_suitable == expected_result
    assert final_log.match_percentage == match_percentage
    assert final_log.threshold == threshold
    assert final_log.result_status == "completed"
