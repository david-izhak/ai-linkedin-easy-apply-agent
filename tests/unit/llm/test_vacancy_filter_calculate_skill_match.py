import logging
from unittest.mock import patch, MagicMock
import pytest
from llm.schemas import MatchResult, SkillsMatch, Experience
from llm.vacancy_filter import calculate_skill_match

# Since we are testing calculate_skill_match, we patch the get_llm_client
# at the point of use inside the vacancy_filter module.
@pytest.fixture
def mock_llm_client():
    """Fixture to mock the LLM client."""
    with patch("llm.vacancy_filter.get_llm_client") as mock_get_llm_client:
        mock_client = MagicMock()
        mock_get_llm_client.return_value = mock_client
        yield mock_client

# Helper function to create default SkillsMatch
def default_skills_match(total=0, matched_count=0, missing_count=0, matched=None, missing=None):
    return SkillsMatch(
        total=total,
        matched_count=matched_count,
        missing_count=missing_count,
        matched=matched or [],
        missing=missing or [],
    )

# Helper function to create default Experience
def default_experience():
    return Experience(
        required_years=None,
        candidate_years=None,
        required_seniority=None,
        candidate_seniority=None,
    )

@pytest.mark.parametrize(
    "match_result, expected_percentage, expected_analysis",
    [
        (
            MatchResult(
                match_percentage=85,
                analysis="Strong match in Python and SQL.",
                required=default_skills_match(5, 4, 1, ["python", "sql"], ["docker"]),
                optional=default_skills_match(3, 2, 1, ["aws", "kubernetes"], ["terraform"]),
                experience=default_experience(),
            ),
            85,
            "Strong match in Python and SQL.",
        ),
        (
            MatchResult(
                match_percentage=0,
                analysis="No overlap.",
                required=default_skills_match(),
                optional=default_skills_match(),
                experience=default_experience(),
            ),
            0,
            "No overlap.",
        ),
        (
            MatchResult(
                match_percentage=100,
                analysis="Perfect fit.",
                required=default_skills_match(5, 5, 0, ["python", "sql", "docker", "aws", "kubernetes"], []),
                optional=default_skills_match(3, 3, 0, ["terraform", "jenkins", "git"], []),
                experience=default_experience(),
            ),
            100,
            "Perfect fit.",
        ),
    ],
)
def test_calculate_skill_match_success(
    mock_llm_client: MagicMock,
    caplog: pytest.LogCaptureFixture,
    match_result: MatchResult,
    expected_percentage: int,
    expected_analysis: str,
    app_config,
):
    """Test skill match calculation with successful structured responses."""
    mock_llm_client.generate_structured_response.return_value = match_result

    with caplog.at_level(logging.INFO):
        percentage, analysis, log_extra = calculate_skill_match(
            1, "description", "resume", app_config
        )

    assert percentage == expected_percentage
    assert analysis == expected_analysis
    assert log_extra["result_status"] == "success_structured"
    mock_llm_client.generate_structured_response.assert_called_once()
    # Check that the schema passed to the structured response is correct
    call_args, call_kwargs = mock_llm_client.generate_structured_response.call_args
    assert call_kwargs.get("schema") is MatchResult


def test_calculate_skill_match_logs_final_info(
    mock_llm_client: MagicMock, caplog: pytest.LogCaptureFixture, app_config
):
    """Test that final structured log is created with all context."""
    mock_response = MatchResult(
        match_percentage=95,
        analysis="Excellent.",
        required=default_skills_match(10, 8, 2, ["python", "sql"], ["docker", "kubernetes"]),
        optional=default_skills_match(5, 4, 1, ["aws", "terraform"], ["jenkins"]),
        experience=default_experience(),
    )
    mock_llm_client.generate_structured_response.return_value = mock_response
    mock_llm_client.provider = "openai"
    mock_llm_client.model = "gpt-4"
    mock_llm_client.max_retries = 3

    with patch("time.time", side_effect=[1000, 1001.5]):
        percentage, analysis, log_extra = calculate_skill_match(
            "vid-123", "job_desc", "resume_text", app_config
        )

    assert log_extra is not None
    assert percentage == 95
    assert analysis == "Excellent."
    assert log_extra["vacancy_id"] == "vid-123"
    assert log_extra["result_status"] == "success_structured"
    assert log_extra["provider"] == "openai"
    assert log_extra["model"] == "gpt-4"
    assert log_extra["latency_ms"] == 1500
    assert log_extra["retries_count"] == 3
