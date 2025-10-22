import sqlite3
import datetime
import logging

DB_FILE = "jobs.db"
logger = logging.getLogger(__name__)


def setup_database():
    """
    Creates the database and tables using job_id as the primary key.
    """
    logger.debug("Setting up database with job_id as PRIMARY KEY...")
    conn = sqlite3.connect(
        DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
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
            seniority_level TEXT,
            employment_type TEXT,
            job_function TEXT,
            industries TEXT,
            company_overview TEXT,
            company_website TEXT,
            company_industry TEXT,
            company_size TEXT
        )
    """
    )

    # Add new columns if they don't exist (for backward compatibility)
    table_info = cursor.execute("PRAGMA table_info(vacancies)").fetchall()
    column_names = [col[1] for col in table_info]
    new_columns = {
        "description": "TEXT",
        "company_description": "TEXT",
        "seniority_level": "TEXT",
        "employment_type": "TEXT",
        "job_function": "TEXT",
        "industries": "TEXT",
        "company_overview": "TEXT",
        "company_website": "TEXT",
        "company_industry": "TEXT",
        "company_size": "TEXT",
    }
    for col, col_type in new_columns.items():
        if col not in column_names:
            logger.info(f"Adding missing column '{col}' to vacancies table.")
            cursor.execute(f"ALTER TABLE vacancies ADD COLUMN {col} {col_type}")

    # Run History table (remains the same)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS run_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TIMESTAMP NOT NULL
        )
    """
    )

    conn.commit()
    conn.close()
    logger.info("Database setup complete.")


def save_discovered_jobs(jobs: list):
    """
    Saves a list of newly discovered jobs to the database.
    """
    if not jobs:
        return
    conn = sqlite3.connect(DB_FILE)
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
    conn.close()


def get_discovered_jobs() -> list:
    """
    Retrieves all jobs with the 'discovered' status, newest first.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, link, title, company FROM vacancies WHERE status = 'discovered' ORDER BY id DESC"
    )
    jobs = cursor.fetchall()
    conn.close()
    logger.info(f"Retrieved {len(jobs)} jobs to be enriched.")
    return jobs


def save_enrichment_data(job_id: int, details: dict):
    """
    Updates a job record with its full scraped details and sets status to 'enriched'.
    """
    logger.debug(f"Enriching job record for job_id: {job_id}")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE vacancies SET
            status = 'enriched',
            description = ?,
            company_description = ?,
            seniority_level = ?,
            employment_type = ?,
            job_function = ?,
            industries = ?,
            company_overview = ?,
            company_website = ?,
            company_industry = ?,
            company_size = ?
        WHERE id = ?
    """,
        (
            details.get("description"),
            details.get("company_description"),
            details.get("seniority_level"),
            details.get("employment_type"),
            details.get("job_function"),
            details.get("industries"),
            details.get("company_overview"),
            details.get("company_website"),
            details.get("company_industry"),
            details.get("company_size"),
            job_id,
        ),
    )
    conn.commit()
    conn.close()


def get_enriched_jobs() -> list:
    """
    Retrieves all jobs with the 'enriched' status, newest first.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Fetch all necessary fields for final filtering and application
    cursor.execute(
        "SELECT id, link, title, company, description FROM vacancies WHERE status = 'enriched' ORDER BY id DESC"
    )
    jobs = cursor.fetchall()
    conn.close()
    logger.info(f"Retrieved {len(jobs)} enriched jobs to be processed.")
    return jobs


def update_job_status(job_id: int, status: str):
    """
    Updates the status of a job identified by its job_id.
    """
    logger.debug(f"Updating status to '{status}' for job_id: {job_id}")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE vacancies SET status = ? WHERE id = ?", (status, job_id))
    conn.commit()
    conn.close()


# --- Unchanged functions ---


def get_last_run_timestamp() -> datetime.datetime | None:
    conn = sqlite3.connect(
        DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )
    cursor = conn.cursor()
    cursor.execute(
        "SELECT run_timestamp FROM run_history ORDER BY run_timestamp DESC LIMIT 1"
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def record_run_timestamp():
    now = datetime.datetime.now()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO run_history (run_timestamp) VALUES (?)", (now,))
    conn.commit()
    conn.close()
    logger.info(f"Recorded new run timestamp: {now}")


def count_todays_applications() -> int:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    cursor.execute(
        "SELECT COUNT(*) FROM vacancies WHERE status = 'applied' AND DATE(created_at) = ?",
        (today_str,),
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count
