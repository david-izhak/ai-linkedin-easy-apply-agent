import sqlite3
import datetime
import logging
import contextlib


logger = logging.getLogger(__name__)


@contextlib.contextmanager
def get_db_connection(db_file: str):
    """Контекстный менеджер для соединения с базой данных."""
    conn = sqlite3.connect(db_file)
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection):
    """
    Creates the database tables on the given connection.
    """
    logger.debug(f"Setting up database tables...")
    cursor = conn.cursor()

    # Vacancies table with job_id as the PRIMARY KEY
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vacancies (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            link TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'discovered',
            created_at TIMESTAMP NOT NULL,
            description TEXT,
            company_description TEXT,
            employment_type TEXT,
            company_overview TEXT,
            company_website TEXT,
            company_industry TEXT,
            company_size TEXT,
            match_percentage INTEGER,
            analysis TEXT
        )
    """
    )
    # Run history table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS run_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TIMESTAMP NOT NULL
        )
    """
    )
    conn.commit()
    logger.info("Database setup complete.")


def setup_database(db_file: str) -> sqlite3.Connection:
    """
    Initializes the database connection and creates tables.
    """
    conn = sqlite3.connect(
        db_file, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False
    )
    init_db(conn)
    return conn


def save_discovered_jobs(jobs: list, conn: sqlite3.Connection):
    """
    Saves a list of newly discovered jobs to the database.
    """
    if not jobs:
        return
    logger.debug(f"Saving {len(jobs)} discovered jobs.")
    cursor = conn.cursor()
    now = datetime.datetime.now()
    jobs_to_insert = [
        (job_id, title, company, link, "discovered", now)
        for job_id, link, title, company in jobs
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO vacancies (id, title, company, link, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        jobs_to_insert,
    )
    conn.commit()
    logger.info(
        f"Saved {cursor.rowcount} new discovered jobs. Ignored {len(jobs_to_insert) - cursor.rowcount} duplicates."
    )


def get_jobs_to_enrich(conn: sqlite3.Connection) -> list:
    """
    Retrieves all jobs with 'discovered' or 'enrichment_error' status, newest first.
    """
    logger.debug("Getting jobs to enrich.")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, link, title, company FROM vacancies WHERE status = 'discovered' OR status = 'enrichment_error' ORDER BY id DESC"
    )
    jobs = cursor.fetchall()
    logger.info(f"Retrieved {len(jobs)} jobs to be enriched.")
    return jobs


def save_enrichment_data(job_id: int, details: dict, conn: sqlite3.Connection):
    """
    Updates a job record with its full scraped details and sets status to 'enriched'.
    """
    logger.debug(f"Enriching job_id: {job_id}")
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE vacancies SET
            status = 'enriched',
            description = ?,
            company_description = ?,
            employment_type = ?,
            company_overview = ?,
            company_website = ?,
            company_industry = ?,
            company_size = ?,
            match_percentage = ?,
            analysis = ?
        WHERE id = ?
    """,
        (
            details.get("description"),
            details.get("company_description"),
            details.get("employment_type"),
            details.get("company_overview"),
            details.get("company_website"),
            details.get("company_industry"),
            details.get("company_size"),
            details.get("match_percentage"),
            details.get("analysis"),
            job_id,
        ),
    )
    conn.commit()


def save_skill_match_data(
    job_id: int, match_percentage: int, analysis: str, conn: sqlite3.Connection
):
    """
    Updates a job record with skill match data.
    """
    logger.debug(f"Saving skill match data for job_id: {job_id}")
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE vacancies SET
            match_percentage = ?,
            analysis = ?
        WHERE id = ?
    """,
        (match_percentage, analysis, job_id),
    )
    conn.commit()


def get_enriched_jobs(conn: sqlite3.Connection) -> list:
    """
    Retrieves all jobs with the 'enriched' status, newest first.
    """
    logger.debug(f"Getting enriched jobs.")
    cursor = conn.cursor()
    # Fetch all necessary fields for final filtering and application
    cursor.execute(
        "SELECT id, link, title, company, description FROM vacancies WHERE status = 'enriched' ORDER BY id DESC"
    )
    jobs = cursor.fetchall()
    logger.info(f"Retrieved {len(jobs)} enriched jobs to be processed.")
    return jobs


def get_error_jobs(conn: sqlite3.Connection) -> list:
    """
    Retrieves all jobs with the 'error' status, newest first.
    
    These are jobs that encountered errors during the application process
    and will be retried in subsequent runs.
    
    Args:
        conn: Database connection object.
        
    Returns:
        list: List of tuples containing (id, link, title, company, description).
    """
    logger.debug(f"Getting jobs with error status for retry.")
    cursor = conn.cursor()
    # Fetch all necessary fields for retry attempt
    cursor.execute(
        "SELECT id, link, title, company, description FROM vacancies WHERE status = 'error' ORDER BY id DESC"
    )
    jobs = cursor.fetchall()
    logger.info(f"Retrieved {len(jobs)} error jobs to be retried.")
    return jobs


def update_job_status(job_id: int, status: str, conn: sqlite3.Connection):
    """
    Updates the status of a job identified by its job_id.
    """
    logger.debug(f"Updating status to '{status}' for job_id: {job_id}")
    cursor = conn.cursor()
    cursor.execute("UPDATE vacancies SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()


# --- Unchanged functions ---


def get_last_run_timestamp(conn: sqlite3.Connection) -> datetime.datetime | None:
    """
    Retrieves the timestamp of the last bot run from the database.
    
    This function is used for monitoring and statistics purposes.
    It is NOT used for calculating job search time periods (which are now
    configured statically via JOB_SEARCH_PERIOD_SECONDS).
    
    Returns:
        datetime.datetime | None: Timestamp of the last run, or None if no runs recorded.
    
    Note:
        This function is maintained for backward compatibility and future analytics.
        See record_run_timestamp() for recording run history.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT run_timestamp FROM run_history ORDER BY run_timestamp DESC LIMIT 1"
    )
    result = cursor.fetchone()
    return result[0] if result else None


def record_run_timestamp(conn: sqlite3.Connection) -> None:
    """
    Records the current timestamp as a bot run in the database.
    
    This function is used for monitoring, statistics, and analytics purposes.
    It is NOT used for calculating job search time periods (which are now
    configured statically via JOB_SEARCH_PERIOD_SECONDS).
    
    The recorded timestamps can be used for:
    - Monitoring bot activity and frequency
    - Generating usage statistics
    - Debugging and troubleshooting
    - Future analytics features
    
    Raises:
        sqlite3.Error: If database operation fails.
    
    Note:
        This function is called at the end of each bot run in main.py.
    """
    now = datetime.datetime.now()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO run_history (run_timestamp) VALUES (?)", (now,))
    conn.commit()
    logger.info(f"Recorded new run timestamp: {now}")


def count_todays_applications(conn: sqlite3.Connection) -> int:
    cursor = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) FROM vacancies WHERE status = 'applied' AND DATE(created_at) = ?",
        (today_str,),
    )
    count = cursor.fetchone()[0]
    return count


def get_vacancy_by_id(vacancy_id: int, conn: sqlite3.Connection) -> dict | None:
    """
    Retrieves a single vacancy by its ID.
    """
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,))
    vacancy = cursor.fetchone()
    if vacancy:
        return dict(vacancy)
    return None


def get_existing_vacancy_ids(
    candidate_ids: list[int], conn: sqlite3.Connection
) -> set[int]:
    if not candidate_ids:
        return set()
    cursor = conn.cursor()
    # Build placeholders for IN clause safely
    placeholders = ",".join(["?"] * len(candidate_ids))
    cursor.execute(
        f"SELECT id FROM vacancies WHERE id IN ({placeholders})",
        candidate_ids,
    )
    rows = cursor.fetchall()
    return {row[0] for row in rows}
