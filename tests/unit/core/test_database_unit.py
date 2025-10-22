import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from core.database import (
    init_db,
    save_discovered_jobs,
    get_jobs_to_enrich,
    update_job_status,
    save_enrichment_data,
    get_enriched_jobs,
)

@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


class TestDatabaseUnit:
    def test_save_discovered_jobs(self, db_conn):
        """Tests saving discovered jobs."""
        jobs = [(1, "/link1", "Title1", "Company1"), (2, "/link2", "Title2", "Company2")]
        save_discovered_jobs(jobs, db_conn)
        
        discovered = get_jobs_to_enrich(db_conn)
        assert len(discovered) == 2
        assert discovered[0][0] == 2  # Ordered by id DESC

    def test_update_job_status(self, db_conn):
        """Tests updating a job's status."""
        jobs = [(1, "/link1", "Title1", "Company1")]
        save_discovered_jobs(jobs, db_conn)
        
        update_job_status(1, "applied", db_conn)
        
        cursor = db_conn.cursor()
        cursor.execute("SELECT status FROM vacancies WHERE id = 1")
        status = cursor.fetchone()[0]
        assert status == "applied"

    def test_save_enrichment_data(self, db_conn):
        """Tests saving enrichment data."""
        jobs = [(1, "/link1", "Title1", "Company1")]
        save_discovered_jobs(jobs, db_conn)
        
        details = {"description": "New description"}
        save_enrichment_data(1, details, db_conn)
        
        enriched = get_enriched_jobs(db_conn)
        assert len(enriched) == 1
        assert enriched[0][4] == "New description"
        assert enriched[0][0] == 1
