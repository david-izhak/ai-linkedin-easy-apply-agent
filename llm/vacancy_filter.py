import logging
import time
from typing import Tuple, Optional

from config import AppConfig
from llm.exceptions import ResumeReadError, VacancyNotFoundError
from llm.prompts import VACANCY_MATCH_PROMPT
from llm.schemas import MatchResult
from core.database import get_db_connection, get_vacancy_by_id, save_skill_match_data
from llm.resume_utils import read_resume_text
from llm.client_factory import get_llm_client
from llm.utils import format_prompt

logger = logging.getLogger(__name__)


def calculate_skill_match(
    vacancy_id: int,
    vacancy_description: str,
    resume_text: str,
    app_config: AppConfig,
) -> Tuple[int, str, dict]:
    """
    Calculate skill match using structured LLM response via Function Calling.
    
    This function uses Function Calling / Tool Use to ensure the LLM returns
    a strictly typed MatchResult instead of free-form text that needs parsing.
    All JSON parsing logic has been removed in favor of structured output.
    """
    llm_client = get_llm_client(app_config.llm)
    prompt = format_prompt(
        VACANCY_MATCH_PROMPT,
        vacancy_description=vacancy_description,
        resume_text=resume_text,
    )

    start_time = time.time()
    
    # Use structured output with Function Calling
    # This guarantees we get a MatchResult object with validated fields
    system_message = (
        "You are a strict scoring engine. Return the result only via structured function output. "
        "Follow the algorithm exactly without subjective judgments."
    )
    
    result: MatchResult = llm_client.generate_structured_response(
        prompt=prompt,
        schema=MatchResult,
        system_message=system_message,
    )
    
    latency_ms = int((time.time() - start_time) * 1000)

    log_extra = {
        "vacancy_id": vacancy_id,
        "provider": llm_client.provider,
        "model": llm_client.model,
        "latency_ms": latency_ms,
        "retries_count": llm_client.max_retries,
        "result_status": "success_structured",
    }

    # Extract validated values from Pydantic model
    match_percentage = result.match_percentage
    analysis = result.analysis

    return match_percentage, analysis, log_extra


async def is_vacancy_suitable(
    vacancy_id: int, app_config: AppConfig
) -> Tuple[bool, Optional[str]]:
    """
    Check if the job is suitable for the candidate using LLM

    Args:
        vacancy_id: Job ID in the database
        app_config: The application configuration object.

    Returns:
        bool: True if the vacancy is suitable, False otherwise

    Raises:
        VacancyNotFoundError: If the vacancy was not found.
        ResumeReadError: If the candidate profile could not be loaded.
        Exception: For other system errors (e.g., LLM unavailable).
    """
    logger.debug(f"Call to function '{__name__}' started.")
    profile_path = str(app_config.modal_flow.profile_path)

    log_extra = {
        "vacancy_id": vacancy_id,
        "profile_path": profile_path,
    }

    try:
        logger.debug(f"Getting vacancy data for ID: {vacancy_id}")
        with get_db_connection(app_config.session.db_file) as conn:
            vacancy_data = get_vacancy_by_id(vacancy_id, conn)

        if not vacancy_data:
            raise VacancyNotFoundError(vacancy_id=vacancy_id)

        vacancy_description = vacancy_data.get("description", "")
        if not vacancy_description:
            log_extra["result_status"] = "no_description"
            logger.warning(
                f"Job vacancy {vacancy_id} has no description.", extra=log_extra
            )
            return False, "No description found"

        resume_text = read_resume_text(app_config)

        match_percentage, analysis, calc_log_extra = calculate_skill_match(
            vacancy_id, vacancy_description, resume_text, app_config
        )

        if isinstance(calc_log_extra, dict):
            log_extra.update(calc_log_extra)
        else:
            log_extra["calc_status"] = str(calc_log_extra)

        suitable = match_percentage >= app_config.llm.LLM_THRESHOLD_PERCENTAGE

        # Save skill match data to database
        with get_db_connection(app_config.session.db_file) as conn:
            save_skill_match_data(
                vacancy_id, match_percentage, analysis, conn
            )

        # Adding final status and log data
        log_extra["match_percentage"] = match_percentage
        log_extra["analysis"] = analysis
        log_extra["is_suitable"] = suitable
        log_extra["threshold"] = app_config.llm.LLM_THRESHOLD_PERCENTAGE
        log_extra["result_status"] = "completed"

        logger.info("Vacancy suitability assessed", extra=log_extra)

        return suitable, f"LLM_THRESHOLD_PERCENTAGE: {app_config.llm.LLM_THRESHOLD_PERCENTAGE}, match_percentage: {match_percentage}, analysis: {analysis}"

    except VacancyNotFoundError as e:
        log_extra["result_status"] = "vacancy_not_found"
        logger.warning(
            f"Vacancy {vacancy_id} was not found in the database.",
            extra=log_extra,
            exc_info=e,
        )
        raise

    except ResumeReadError as e:
        log_extra["result_status"] = "resume_read_error"
        logger.error(
            f"Error loading candidate profile for vacancy {vacancy_id}",
            extra=log_extra,
            exc_info=e,
        )
        raise

    except Exception as e:
        log_extra["result_status"] = "error"
        logger.exception(
            f"An unknown error occurred while checking the vacancy. {vacancy_id}. Exception: {str(e)[:100]}",
            extra=log_extra,
        )
        raise
