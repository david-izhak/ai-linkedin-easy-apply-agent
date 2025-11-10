import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class LoginConfig(BaseSettings):
    """Configuration for LinkedIn login credentials."""

    email: str = Field(..., validation_alias="LINKEDIN_EMAIL")
    password: str = Field(..., validation_alias="LINKEDIN_PASSWORD")


class SessionConfig(BaseSettings):
    """Configuration for user session data."""

    user_data_dir: Path = Path("./linkedin_session")
    db_file: Optional[str] = "jobs.db"
    db_conn: Optional[sqlite3.Connection] = Field(None, exclude=True)

    class Config:
        arbitrary_types_allowed = True


class LoggingConfig(BaseSettings):
    """Configuration for logging."""

    log_level: str = "DEBUG"  # DEBUG, INFO, WARNING, ERROR
    log_format: str = "json"  # json, console
    log_file_path: Path = Path("./logs/application.log")
    metrics_file_path: Path = Path("./logs/metrics.json")


class ResilienceConfig(BaseSettings):
    """Configuration for resilience features like retries and circuit breakers."""

    max_attempts: int = 3
    initial_wait: float = 1.0  # seconds
    max_wait: float = 10.0  # seconds
    exponential_base: int = 2
    jitter: bool = True


class CircuitBreakerConfig(BaseSettings):
    """Configuration for the circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: int = 60  # seconds
    expected_exception: type = Exception

    class Config:
        arbitrary_types_allowed = True


class SelectorRetryOverrideConfig(BaseSettings):
    """Configuration for per-selector retry overrides."""

    overrides: Dict[str, Dict[str, Any]] = {
        "easy_apply_button_enabled": {"max_attempts": 5, "initial_wait": 2.0},
        "submit": {"max_attempts": 1, "initial_wait": 0},
    }


class JobSearchConfig(BaseSettings):
    """Parameters for job searching."""

    keywords: str = "Software Engineer"
    geo_id: str = "118490091"
    distance: str = "20"
    job_search_period_seconds: int = 2592000  # 30 days in seconds / 7 days = 604800 / 2 days = 172800 / 1 day = 86400
    sort_by: str = "DD"  # DD = Date Descending, R = Relevance
    job_title_regex: str = r"(?i)^(?!.*(frontend|rust|laravel|php|junior|angular|driver|go(lang)|architect|qa|unity|technical|lead|teamlead|devops|salesforce|technology|llm|embedded|hardware|android|firmware|c\+\+|\.net|c#)).*?(automation|staff|sw|solution(s)|software|java|python|data|back\s*end|ai|chatbot|principal|full\s*stack|senior).*?.*?(developer|engineer).*$"
    job_description_regex: str = r".*"
    job_description_languages: List[str] = ["en", "ru"]

    model_config = SettingsConfigDict(validate_assignment=True)


class WorkplaceConfig(BaseSettings):
    """Configuration for workplace types."""

    remote: bool = True
    on_site: bool = True
    hybrid: bool = True


def _load_profile_data() -> Dict[str, Any]:
    """Загружает данные профиля из JSON-файла."""
    profile_path = Path(__file__).parent / "config" / "profile_example.json"
    if profile_path.exists():
        with open(profile_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class FormDataConfig(BaseSettings):
    """Configuration for filling out job application forms."""

    phone: str = Field(..., validation_alias="PHONE")
    cv_path: Path = Field(..., validation_alias="CV_PATH")
    cover_letter_path: Optional[Path] = None
    delete_cover_letter_after_use: bool = Field(
        True, validation_alias="DELETE_COVER_LETTER_AFTER_USE"
    )
    home_city: str = "Rishon LeZion, Israel"
    years_of_experience: Dict[str, int] = Field(default_factory=lambda: _load_profile_data().get("years_experience", {}))
    language_proficiency: Dict[str, str] = {
        "english": "professional",
        "russian": "native",
        "hebrew": "beginner",
    }
    requires_visa_sponsorship: bool = False
    text_fields: Dict[str, str] = {"salary": "35k"}
    booleans: Dict[str, bool] = {"bachelhor|bacharelado": True, "authorized": True}
    multiple_choice_fields: Dict[str, str] = {"pronouns": "He/him"}


class GeneralSettingsConfig(BaseSettings):
    """Other general settings for the bot."""

    single_page: bool = False
    browser_headless: bool = False
    max_applications_per_day: int = 30
    wait_between_enrichments_ms: int = 10000
    wait_between_submissions_ms: int = 30000


class BotModeConfig(BaseSettings):
    """Configuration for the bot's operating mode."""

    mode: str = Field("processing", validation_alias="BOT_MODE")
    valid_modes: List[str] = [
        "discovery",
        "enrichment",
        "processing",
        "processing_submit",
        "full_run",
        "full_run_submit",
        "test_logging",
    ]

    @model_validator(mode="after")
    def check_valid_mode(self) -> "BotModeConfig":
        if self.mode not in self.valid_modes:
            raise ValueError(
                f"Invalid BOT_MODE: {self.mode}. Must be one of {self.valid_modes}"
            )
        return self


class JobLimitsConfig(BaseSettings):
    """Settings for limiting job processing (for testing/minimal runs)."""

    max_jobs_to_discover: Optional[int] = 0
    max_jobs_to_enrich: Optional[int] = 0
    max_jobs_to_process: Optional[int] = 4


class PerformanceConfig(BaseSettings):
    """Timeout settings for performance optimization."""

    networkidle_timeout: int = 60000  # ms
    max_wait_ms: int = 30000  # ms
    poll_interval_ms: int = 200  # ms
    selector_timeout: int = 5000  # ms
    max_noncritical_consecutive_errors: int = 5


class DiagnosticsConfig(BaseSettings):
    """Diagnostics collection settings for failures."""

    enable_on_failure: bool = False
    capture_screenshot: bool = True
    capture_html: bool = True
    capture_console_log: bool = True
    capture_har: bool = False
    capture_trace: bool = False
    output_dir: Path = Path("./logs/diagnostics")
    max_artifacts_per_run: int = 10
    pii_mask_patterns: List[str] = []
    phases_enabled: List[str] = ["discovery", "enrichment", "processing"]


class LLMSettings(BaseSettings):
    """LLM Configuration"""

    model_config = SettingsConfigDict(frozen=True)

    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "ep-4rgm7z-1761497796779465664"
    LLM_THRESHOLD_PERCENTAGE: int = 70
    LLM_TIMEOUT: int = 300
    LLM_MAX_RETRIES: int = 3
    LLM_BASE_URL: Optional[
        str
    ] = "https://vanchin.streamlake.ai/api/gateway/v1/endpoints"
    LLM_TEMPERATURE: float = 0.0
    LLM_API_KEY: str = ""

    @field_validator("LLM_THRESHOLD_PERCENTAGE")
    @classmethod
    def threshold_must_be_in_range(cls, v: int) -> int:
        if not (0 <= v <= 100):
            raise ValueError("must be between 0 and 100")
        return v

    @model_validator(mode="after")
    def check_api_key_for_provider(self) -> "LLMSettings":
        if self.LLM_PROVIDER in ["openai", "anthropic", "google"] and not self.LLM_API_KEY:
            if self.LLM_BASE_URL and "localhost" in self.LLM_BASE_URL:
                return self
            raise ValueError(
                "LLM_API_KEY is required for openai/anthropic/google providers. Please set it in your .env file."
            )
        return self


class ModalFlowLearningSettings(BaseSettings):
    """Learning configuration for modal flow rule auto-generation."""

    enabled: bool = True
    auto_learn: bool = True
    use_separate_rule_generation: bool = True  # Use separate LLM call for rule generation
    rule_generation_fallback: bool = True  # Use suggest_rule from decision as fallback
    confidence_threshold: float = 0.85
    enable_duplicate_check: bool = True
    enable_pattern_validation: bool = True
    enable_strategy_validation: bool = True
    review_mode: bool = False
    review_path: Optional[Path] = Path("config/pending_rules.yaml")

    @field_validator("confidence_threshold")
    @classmethod
    def confidence_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        return v


class ModalFlowConfig(BaseSettings):
    """Configuration for modal flow based form filling."""

    profile_path: Path = Path("config/profile_example.json")
    rules_path: Path = Path("config/rules.yaml")
    normalizer_rules_path: Optional[Path] = Path("config/normalizer_rules.yaml")
    max_steps: int = 16
    llm_delegate_enabled: bool = True
    learning: ModalFlowLearningSettings = ModalFlowLearningSettings()


class AppConfig(BaseSettings):
    """Root configuration class for the application."""

    login: LoginConfig = LoginConfig()
    session: SessionConfig = SessionConfig()
    logging: LoggingConfig = LoggingConfig()
    resilience: ResilienceConfig = ResilienceConfig()
    circuit_breaker: CircuitBreakerConfig = CircuitBreakerConfig()
    selector_retry_overrides: SelectorRetryOverrideConfig = (
        SelectorRetryOverrideConfig()
    )
    job_search: JobSearchConfig = JobSearchConfig()
    workplace: WorkplaceConfig = WorkplaceConfig()
    form_data: FormDataConfig = FormDataConfig()
    general_settings: GeneralSettingsConfig = GeneralSettingsConfig()
    bot_mode: BotModeConfig = BotModeConfig()
    job_limits: JobLimitsConfig = JobLimitsConfig()
    performance: PerformanceConfig = PerformanceConfig()
    diagnostics: DiagnosticsConfig = DiagnosticsConfig()
    llm: LLMSettings = LLMSettings()
    modal_flow: ModalFlowConfig = ModalFlowConfig()

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Instantiate the main config object
config = AppConfig()
