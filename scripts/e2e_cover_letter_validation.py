"""
End-to-end manual validation script for cover letter generation.

Поддерживаемые провайдеры:
- LLM_PROVIDER=ollama    -> локальный Ollama (http://localhost:11434)
- LLM_PROVIDER=openai    -> OpenAI-совместимые API (в т.ч. OpenRouter) через ChatOpenAI
- LLM_PROVIDER=anthropic -> Anthropic через ChatAnthropic

Скрипт:
- Настраивает окружение так, чтобы llm.llm_client.LLMClient видел корректные переменные.
- Для Ollama проверяет доступность демона и модели (и при необходимости делает pull).
- Для OpenAI/OpenRouter/Anthropic делает health-check endpoint'ов.
- Патчит зависимости cover_letter_generator для самодостаточного прогона.
- Выполняет позитивный и негативные сценарии, валидирует результат и пишет логи/итоги.

Запуск:
  python scrypts/e2e_cover_letter_validation.py
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, Tuple, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import urllib.parse
import sys

# ---------- Project path ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------- Load .env ----------
load_dotenv()

# ---------- Configuration ----------
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "generated_letters_e2e"
LOGS_DIR = BASE_DIR / "logs"
RESULTS_JSON = LOGS_DIR / "e2e_results.json"
LOG_FILE = LOGS_DIR / "e2e_cover_letter_validation.log"

# Read env with sane defaults
DEFAULT_PROVIDER = os.environ.get(
    "LLM_PROVIDER", "ollama"
).lower()  # ollama | openai | anthropic
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")

# For ollama we keep http://localhost:11434 by default.
DEFAULT_LLM_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434")
DEFAULT_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.0"))
DEFAULT_TIMEOUT_SEC = int(os.environ.get("LLM_TIMEOUT", "300"))
DEFAULT_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "3"))
DEFAULT_API_KEY = os.environ.get("LLM_API_KEY", "")

SUCCESS_VACANCY_ID = 101
NOT_FOUND_VACANCY_ID = 999


# ---------- Logging ----------
def setup_logging() -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("e2e")
    logger.setLevel(logging.DEBUG)

    # Console
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))

    # File
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # Reset handlers for re-runs
    for h in list(logger.handlers):
        logger.removeHandler(h)
    logger.addHandler(ch)
    logger.addHandler(fh)

    logging.getLogger("llm").setLevel(logging.DEBUG)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    return logger


# ---------- Minimal HTTP JSON ----------
def _http_json(
    method: str,
    url: str,
    headers: Dict[str, str] | None = None,
    data: Dict[str, Any] | None = None,
    timeout: int = 10,
) -> Tuple[int, Any]:
    _headers = {"Content-Type": "application/json"}
    if headers:
        _headers.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = Request(url, data=body, headers=_headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
            try:
                return status, json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return status, raw.decode("utf-8")
    except HTTPError as e:
        payload = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        try:
            return e.code, json.loads(payload)
        except Exception:
            return e.code, {"error": payload}
    except URLError as e:
        return 0, {"error": str(e)}


# ---------- Environment setup ----------
def configure_environment(logger: logging.Logger) -> None:
    """
    Конфигурируем ENV *до* импортов модулей llm.*, чтобы LLMClient увидел корректные значения.
    Также устанавливаем переменные, ожидаемые драйверами LangChain.
    """
    os.environ["LLM_PROVIDER"] = DEFAULT_PROVIDER
    os.environ["LLM_MODEL"] = DEFAULT_MODEL
    os.environ["LLM_BASE_URL"] = DEFAULT_LLM_URL
    os.environ["LLM_TEMPERATURE"] = str(DEFAULT_TEMPERATURE)
    os.environ["LLM_TIMEOUT"] = str(DEFAULT_TIMEOUT_SEC)
    os.environ["LLM_MAX_RETRIES"] = str(DEFAULT_MAX_RETRIES)
    os.environ["LLM_API_KEY"] = DEFAULT_API_KEY

    # Для ChatOpenAI (OpenAI / OpenRouter): LangChain читает OPENAI_API_BASE/OPENAI_API_KEY
    if DEFAULT_PROVIDER == "openai":
        os.environ["OPENAI_API_BASE"] = DEFAULT_LLM_URL
        os.environ["OPENAI_API_KEY"] = DEFAULT_API_KEY

    # Для Anthropic: библиотека читает ключ из аргумента, но health-check используем прямой HTTP
    # Дополнительно можно выставить ANTHROPIC_API_KEY для совместимости с тулзами
    if DEFAULT_PROVIDER == "anthropic":
        os.environ.setdefault("ANTHROPIC_API_KEY", DEFAULT_API_KEY)

    # Резервный путь к резюме, хотя мы патчим чтение
    os.environ.setdefault("RESUME_TXT_PATH", str(BASE_DIR / "tmp_resume.txt"))

    logger.info(
        f"ENV configured | provider={DEFAULT_PROVIDER} model={DEFAULT_MODEL} base_url={DEFAULT_LLM_URL} "
        f"temp={DEFAULT_TEMPERATURE} timeout={DEFAULT_TIMEOUT_SEC}s retries={DEFAULT_MAX_RETRIES}"
    )


# ---------- Provider-specific health/model checks ----------
def ensure_ready_ollama(logger: logging.Logger, base_url: str) -> bool:
    st, payload = _http_json("GET", urllib.parse.urljoin(base_url, "/api/version"))
    if st == 200:
        logger.info(f"Ollama reachable. Version: {payload}")
        return True
    logger.error(f"Ollama not reachable at {base_url}. Response: {payload}")
    return False


def ensure_model_ollama(
    logger: logging.Logger,
    base_url: str,
    model: str,
    pull_if_missing: bool = True,
    pull_timeout_sec: int = 600,
) -> bool:
    st, payload = _http_json("GET", urllib.parse.urljoin(base_url, "/api/tags"))
    if st != 200:
        logger.error(f"Failed to list Ollama models. Status={st}, payload={payload}")
        return False
    names = {
        m.get("name")
        for m in (payload.get("models", []) if isinstance(payload, dict) else [])
    }
    if model in names:
        logger.info(f"Ollama model '{model}' is present.")
        return True

    if not pull_if_missing:
        logger.error(f"Ollama model '{model}' not present and auto-pull disabled.")
        return False

    logger.info(f"Pulling Ollama model '{model}'...")
    st2, payload2 = _http_json(
        "POST",
        urllib.parse.urljoin(base_url, "/api/pull"),
        data={"name": model},
        timeout=pull_timeout_sec,
    )
    if st2 == 200:
        # re-check
        st3, payload3 = _http_json("GET", urllib.parse.urljoin(base_url, "/api/tags"))
        names2 = {
            m.get("name")
            for m in (payload3.get("models", []) if isinstance(payload3, dict) else [])
        }
        if model in names2:
            logger.info(f"Ollama model '{model}' present after pull.")
            return True
    logger.error(
        f"Failed to pull Ollama model '{model}'. Status={st2}, payload={payload2}"
    )
    return False


def ensure_ready_openai_like(
    logger: logging.Logger, base_url: str, api_key: str
) -> bool:
    """
    OpenAI-совместимые API (включая OpenRouter): GET {base}/models с Bearer-токеном.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    st, payload = _http_json(
        "GET",
        urllib.parse.urljoin(base_url.rstrip("/") + "/", "models"),
        headers=headers,
    )
    if st == 200:
        logger.info("OpenAI-compatible endpoint reachable.")
        return True
    logger.error(
        f"OpenAI-compatible endpoint not reachable. Status={st} payload={payload}"
    )
    return False


def ensure_ready_anthropic(logger: logging.Logger, base_url: str, api_key: str) -> bool:
    """
    Anthropic API health: GET {base}/models с нужными заголовками.
    По умолчанию base=https://api.anthropic.com/v1, если не задан.
    """
    base = base_url or "https://api.anthropic.com/v1"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    st, payload = _http_json(
        "GET", urllib.parse.urljoin(base.rstrip("/") + "/", "models"), headers=headers
    )
    if st == 200:
        logger.info("Anthropic endpoint reachable.")
        return True
    logger.error(f"Anthropic endpoint not reachable. Status={st} payload={payload}")
    return False


# ---------- Timeout helper ----------
def run_with_timeout(func: Callable, timeout_sec: int, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as executor:
        fut = executor.submit(func, *args, **kwargs)
        try:
            return fut.result(timeout=timeout_sec)
        except TimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout_sec} seconds")


# ---------- Validation ----------
def _word_count(text: str) -> int:
    return len([w for w in text.strip().split() if w])


def validate_cover_letter(text: str, context: Dict[str, Any]) -> Dict[str, Any]:
    results = {"passed": True, "checks": []}
    wc = _word_count(text)
    length_ok = 200 <= wc <= 420
    results["checks"].append(
        {"check": "length_200_420_words", "value": wc, "passed": length_ok}
    )
    if not length_ok:
        results["passed"] = False

    no_md_headers = ("#" not in text) and ("**" not in text)
    results["checks"].append({"check": "no_markdown_headers", "passed": no_md_headers})
    if not no_md_headers:
        results["passed"] = False

    contains_company = context["company_name"] in text
    contains_job_title = context["job_title"] in text
    results["checks"].append(
        {"check": "contains_company_name", "passed": contains_company}
    )
    results["checks"].append(
        {"check": "contains_job_title", "passed": contains_job_title}
    )
    if not (contains_company and contains_job_title):
        results["passed"] = False

    has_numbers = any(ch.isdigit() for ch in text)
    results["checks"].append(
        {"check": "contains_numeric_achievements", "passed": has_numbers}
    )
    if not has_numbers:
        results["passed"] = False

    return results


# ---------- Module patching ----------
def patch_cover_letter_module(logger: logging.Logger) -> Dict[str, Any]:
    from llm import cover_letter_generator as clg
    from llm import exceptions as llm_exc
    from llm import client_factory as cf

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clg.settings.GENERATED_LETTERS_DIR = str(OUTPUT_DIR)
    logger.info(
        f"Patched clg.settings.GENERATED_LETTERS_DIR = {clg.settings.GENERATED_LETTERS_DIR}"
    )

    # --- NEW: путь к JSON с вакансиями в той же папке, что и скрипт ---
    vacancies_path = BASE_DIR / "vacancies.json"

    def _mock_get_vacancy_by_id(vacancy_id: int) -> Dict[str, str] | None:
        """
        Динамически загружает данные вакансий из vacancies.json и возвращает
        словарь по нужному id либо None, если не найдено/файл некорректен.
        Допускает две структуры JSON:
          1) [{"id": 101, ...}, {"id": 999, ...}]
          2) {"vacancies": [{...}, {...}]}
        """
        try:
            with vacancies_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error(f"Vacancies file not found: {vacancies_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {vacancies_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to read {vacancies_path}: {type(e).__name__}: {e}")
            return None

        items = None
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict) and isinstance(data.get("vacancies"), list):
            items = data["vacancies"]
        else:
            logger.error(f"Unexpected vacancies JSON structure in {vacancies_path}")
            return None

        # Ищем по id (строгое приведение к str для совместимости типов)
        target = next((v for v in items if str(v.get("id")) == str(vacancy_id)), None)
        if not target:
            logger.info(f"Vacancy id={vacancy_id} not found in {vacancies_path}")
            return None

        # Приводим ключи к ожидаемым именам (оставляя разумные дефолты)
        return {
            "title": target.get("title") or target.get("job_title", ""),
            "company": target.get("company") or target.get("company_name", ""),
            "description": target.get("description")
            or target.get("job_description", ""),
            "location": target.get("location", ""),
            "company_description": target.get(
                "company_description", target.get("company_overview", "")
            ),
            "seniority_level": target.get("seniority_level", ""),
            "employment_type": target.get("employment_type", ""),
            "job_function": target.get("job_function", ""),
            "industries": target.get("industries", target.get("industry", "")),
            "company_overview": target.get("company_overview", ""),
            "company_website": target.get("company_website", target.get("website", "")),
            "company_industry": target.get(
                "company_industry", target.get("industry", "")
            ),
            "company_size": target.get("company_size", ""),
        }

    clg.get_vacancy_by_id = _mock_get_vacancy_by_id
    logger.info("Patched clg.get_vacancy_by_id with self-contained mock.")

    def _mock_read_resume_text(path: str) -> str:
        """
        Загружает текст резюме из внешнего .txt файла.

        Порядок разрешения пути:
          1) аргумент `path` (если относительный — трактуется относительно BASE_DIR),
          2) переменная окружения RESUME_TXT_PATH,
          3) файл BASE_DIR / "tmp_resume.txt".

        При неудаче — бросает ResumeReadError (как ожидает генератор).
        """
        candidates: list[Path] = []

        # 1) Явный путь из аргумента
        if path:
            p = Path(path)
            candidates.append(p if p.is_absolute() else (BASE_DIR / p))

        # 2) Путь из ENV
        env_path = os.environ.get("RESUME_TXT_PATH", "")
        if env_path:
            p = Path(env_path)
            candidates.append(p if p.is_absolute() else (BASE_DIR / p))

        # 3) Дефолт в той же директории, что и скрипт
        candidates.append(BASE_DIR / "tmp_resume.txt")

        tried: list[str] = []
        for cp in candidates:
            try:
                tried.append(str(cp))
                if cp.exists() and cp.is_file():
                    text = cp.read_text(encoding="utf-8")
                    logger.info(f"Read resume from: {cp}")
                    return text
            except Exception as e:
                logger.warning(
                    f"Failed to read resume from {cp}: {type(e).__name__}: {e}"
                )

        # Если ни один кандидат не сработал — поведение, совместимое с остальным кодом
        raise llm_exc.ResumeReadError(
            str(candidates[0] if candidates else path),
            message="Failed to read resume file. Tried: " + " | ".join(tried),
        )

    clg.read_resume_text = _mock_read_resume_text
    logger.info("Patched clg.read_resume_text with self-contained mock.")

    cf.get_llm_client.cache_clear()
    logger.info("Cleared llm.client_factory.get_llm_client cache.")

    from llm.llm_client import LLMClient as _RealLLMClient

    def _patched_get_llm_client():
        return _RealLLMClient()

    clg.get_llm_client = _patched_get_llm_client
    logger.info("Patched clg.get_llm_client to use LLMClient.")

    return {"clg": clg, "exceptions": llm_exc, "client_factory": cf}


# ---------- Phases ----------
def phase_success_generation(logger: logging.Logger, clg_module) -> Dict[str, Any]:
    context = {
        "job_title": clg_module.get_vacancy_by_id(SUCCESS_VACANCY_ID)["title"],
        "company_name": clg_module.get_vacancy_by_id(SUCCESS_VACANCY_ID)["company"],
    }
    cover_text = run_with_timeout(
        clg_module.generate_cover_letter,
        DEFAULT_TIMEOUT_SEC,
        SUCCESS_VACANCY_ID,
        str(BASE_DIR / "tmp_resume.txt"),
    )
    logger.info("Cover letter generated in success phase.")

    validation = validate_cover_letter(cover_text, context)
    if not validation["passed"]:
        logger.warning(
            f"Validation failed checks: {json.dumps(validation, ensure_ascii=False)}"
        )
    else:
        logger.info("Validation passed for generated cover letter.")

    filepath = clg_module.save_cover_letter(SUCCESS_VACANCY_ID, cover_text)
    exists = Path(filepath).exists()
    logger.info(f"Cover letter saved to: {filepath} (exists={exists})")

    return {
        "phase": "success_generation",
        "file": filepath,
        "exists": exists,
        "validation": validation,
    }


def phase_vacancy_not_found(
    logger: logging.Logger, clg_module, exceptions_module
) -> Dict[str, Any]:
    passed, error_message = False, ""
    try:
        _ = clg_module.generate_cover_letter(
            NOT_FOUND_VACANCY_ID, str(BASE_DIR / "tmp_resume.txt")
        )
    except exceptions_module.VacancyNotFoundError as e:
        passed, error_message = True, str(e)
        logger.info(f"VacancyNotFoundError captured as expected: {error_message}")
    except Exception as e:
        error_message = f"Unexpected exception: {type(e).__name__}: {e}"
        logger.error(error_message)
    return {"phase": "vacancy_not_found", "passed": passed, "error": error_message}


def phase_resume_read_error(
    logger: logging.Logger, clg_module, exceptions_module
) -> Dict[str, Any]:
    original_reader = clg_module.read_resume_text

    def _raise_resume_error(path: str) -> str:
        raise exceptions_module.ResumeReadError(
            path, message="Failed to read resume file at: " + path
        )

    clg_module.read_resume_text = _raise_resume_error
    passed, error_message = False, ""
    try:
        _ = clg_module.generate_cover_letter(SUCCESS_VACANCY_ID, "nonexistent.txt")
    except exceptions_module.ResumeReadError as e:
        passed, error_message = True, str(e)
        logger.info(f"ResumeReadError captured as expected: {error_message}")
    except Exception as e:
        error_message = f"Unexpected exception: {type(e).__name__}: {e}"
        logger.error(error_message)
    finally:
        clg_module.read_resume_text = original_reader
    return {"phase": "resume_read_error", "passed": passed, "error": error_message}


def phase_llm_failure(
    logger: logging.Logger, clg_module, exceptions_module
) -> Dict[str, Any]:
    original_get_llm_client = clg_module.get_llm_client

    class _FailingClient:
        def generate_response(self, prompt: str) -> str:
            raise exceptions_module.LLMGenerationError(
                message="Simulated LLM failure",
                prompt=prompt,
                provider=DEFAULT_PROVIDER,
                model=DEFAULT_MODEL,
            )

    clg_module.get_llm_client = lambda: _FailingClient()
    passed, error_message = False, ""
    try:
        _ = clg_module.generate_cover_letter(
            SUCCESS_VACANCY_ID, str(BASE_DIR / "tmp_resume.txt")
        )
    except exceptions_module.CoverLetterGenerationError as e:
        passed, error_message = True, str(e)
        logger.info(f"CoverLetterGenerationError captured as expected: {error_message}")
    except Exception as e:
        error_message = f"Unexpected exception: {type(e).__name__}: {e}"
        logger.error(error_message)
    finally:
        clg_module.get_llm_client = original_get_llm_client
    return {"phase": "llm_failure", "passed": passed, "error": error_message}


# ---------- Main ----------
def main() -> None:
    logger = setup_logging()
    logger.info("==== E2E Cover Letter Validation: Initialization ====")

    # 1) ENV
    configure_environment(logger)

    # 2) Health / model checks per provider
    logger.info("==== E2E Cover Letter Validation: LLM Checks ====")
    provider = DEFAULT_PROVIDER
    base_url = DEFAULT_LLM_URL
    api_key = DEFAULT_API_KEY

    reachable = False
    if provider == "ollama":
        reachable = ensure_ready_ollama(logger, base_url)
        if reachable:
            reachable = ensure_model_ollama(
                logger, base_url, DEFAULT_MODEL, pull_if_missing=True
            )
    elif provider == "openai":
        reachable = ensure_ready_openai_like(
            logger, os.environ.get("OPENAI_API_BASE", base_url), api_key
        )
    elif provider == "anthropic":
        # Если LLM_BASE_URL пуст, используем дефолтный Anthropic endpoint
        anth_base = base_url or "https://api.anthropic.com/v1"
        reachable = ensure_ready_anthropic(logger, anth_base, api_key)
    else:
        logger.error(f"Unsupported provider in ENV: {provider}")
        reachable = False

    if not reachable:
        logger.error("LLM endpoint not reachable or model missing. Aborting.")
        results = {
            "status": "aborted",
            "reason": "llm_unreachable_or_missing_model",
            "provider": provider,
            "model": DEFAULT_MODEL,
            "base_url": base_url,
        }
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return

    # 3) Patch modules
    logger.info("==== E2E Cover Letter Validation: Patching Module ====")
    modules = patch_cover_letter_module(logger)
    clg = modules["clg"]
    exceptions_module = modules["exceptions"]

    # 4) Phases
    logger.info("==== E2E Cover Letter Validation: Execution Phases ====")
    phase_results = []
    try:
        phase_results.append(phase_success_generation(logger, clg))
        phase_results.append(phase_vacancy_not_found(logger, clg, exceptions_module))
        phase_results.append(phase_resume_read_error(logger, clg, exceptions_module))
        phase_results.append(phase_llm_failure(logger, clg, exceptions_module))

        all_ok = all(
            (
                pr.get("passed", True)
                if pr["phase"] != "success_generation"
                else pr["exists"] and pr["validation"]["passed"]
            )
            for pr in phase_results
        )
        status = "passed" if all_ok else "failed"

        results = {
            "status": status,
            "provider": provider,
            "model": DEFAULT_MODEL,
            "base_url": base_url,
            "phases": phase_results,
            "output_dir": str(OUTPUT_DIR),
            "log_file": str(LOG_FILE),
        }
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (logger.info if status == "passed" else logger.warning)(
            f"==== E2E Cover Letter Validation: {status.upper()} ===="
        )
    except TimeoutError as te:
        logger.error(f"Global timeout error: {te}")
        results = {"status": "failed", "reason": "global_timeout", "error": str(te)}
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.exception("Unexpected error in orchestrator")
        results = {"status": "failed", "reason": "unexpected_error", "error": str(e)}
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
