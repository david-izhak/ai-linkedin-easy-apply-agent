import pytest
import sqlite3
from unittest.mock import patch
import sys
from core import database
from dataclasses import dataclass, field
from unittest.mock import MagicMock

# Adjust the python path to import the module
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from config import (
    AppConfig,
    LoginConfig,
    SessionConfig,
    LoggingConfig,
    ResilienceConfig,
    CircuitBreakerConfig,
    SelectorRetryOverrideConfig,
    JobSearchConfig,
    WorkplaceConfig,
    FormDataConfig,
    GeneralSettingsConfig,
    BotModeConfig,
    JobLimitsConfig,
    PerformanceConfig,
    LLMSettings,
)


@dataclass
class MockJobSearchConfig:
    job_description_regex: str = "python"
    job_description_languages: list[str] = field(default_factory=lambda: ["en"])


@dataclass
class MockSessionConfig:
    db_file: str = "test.db"


@dataclass
class MockLLMSettings:
    LLM_API_KEY: str = "test_key"
    LLM_PROVIDER: str = "openai"


@dataclass
class MockJobLimitsConfig:
    max_jobs_to_enrich: int | None = None


@dataclass(frozen=True)
class GeneralSettingsConfig:
    """Other general settings for the bot."""
    single_page: bool = False
    browser_headless: bool = False
    max_applications_per_day: int = 30
    wait_between_enrichments_ms: int = 0
    wait_between_submissions_ms: int = 0


@dataclass
class MockAppConfig:
    job_search: MockJobSearchConfig = field(default_factory=MockJobSearchConfig)
    session: MockSessionConfig = field(default_factory=MockSessionConfig)
    job_limits: MockJobLimitsConfig = field(default_factory=MockJobLimitsConfig)
    general_settings: GeneralSettingsConfig = field(
        default_factory=GeneralSettingsConfig
    )
    llm_settings: MockLLMSettings = field(default_factory=MockLLMSettings)


@pytest.fixture
def mock_app_config():
    """Fixture for a mock AppConfig."""
    return MockAppConfig()


@pytest.fixture
def app_config(monkeypatch):
    """Pytest fixture for providing a complete AppConfig object for testing."""
    monkeypatch.setenv("LINKEDIN_EMAIL", "test@example.com")
    monkeypatch.setenv("LINKEDIN_PASSWORD", "password")
    monkeypatch.setenv("BOT_MODE", "full_run_submit")
    monkeypatch.setenv("JOB_SEARCH_KEYWORDS", "test")
    monkeypatch.setenv("JOB_TITLE_REGEX", ".*")
    monkeypatch.setenv("JOB_DESCRIPTION_REGEX", ".*")
    monkeypatch.setenv("CV_PATH", "test_cv.pdf")
    monkeypatch.setenv("WAIT_BETWEEN_ENRICHMENTS_MS", "0")
    monkeypatch.setenv("WAIT_BETWEEN_SUBMISSIONS_MS", "0")
    monkeypatch.setenv("MAX_JOBS_TO_DISCOVER", "5")
    monkeypatch.setenv("MAX_JOBS_TO_ENRICH", "5")
    monkeypatch.setenv("MAX_JOBS_TO_PROCESS", "1")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_API_KEY", "test_key")
    monkeypatch.setenv("LLM_THRESHOLD_PERCENTAGE", "70")

    # Clear all env vars that might be set from a .env file
    # to ensure tests are isolated
    for key in os.environ:
        if key.startswith("LINKEDIN_") or key.startswith("BOT_"):
            monkeypatch.delenv(key, raising=False)

    return AppConfig()

