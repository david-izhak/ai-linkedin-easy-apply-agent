# Adjust the python path to import the module
import sys
import os
import pytest
import sqlite3
from core import database

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    database.init_db(conn)
    yield conn
    conn.close()


class TestDatabaseFlow:
    def test_happy_path_job_lifecycle(self, db_conn):
        """Tests the complete lifecycle of a job entry in the database."""
        # 1. Discover: Save a new job
        discovered_jobs = [(123, "/job-link", "Software Engineer", "TestCorp")]
        database.save_discovered_jobs(discovered_jobs, db_conn)

        # Verify it's in the 'discovered' state
        retrieved_jobs = database.get_jobs_to_enrich(db_conn)
        assert len(retrieved_jobs) == 1
        assert retrieved_jobs[0][0] == 123

        # 2. Enrich: Update the job with more details
        enrichment_data = {"description": "Job description here.", "company_description": "A great place to work."}
        database.save_enrichment_data(123, enrichment_data, db_conn)

        # Verify it's now in the 'enriched' state and discovered jobs are gone
        retrieved_enriched = database.get_enriched_jobs(db_conn)
        assert len(retrieved_enriched) == 1
        assert retrieved_enriched[0][0] == 123

        # After enrichment, there should be no more jobs to enrich.
        assert not database.get_jobs_to_enrich(db_conn)

        # 3. Process: Update the job status to 'applied'
        database.update_job_status(123, "applied", db_conn)

        # Verify it's no longer in 'enriched'
        assert not database.get_enriched_jobs(db_conn)

        # Optional: Verify final state with a direct query
        cursor = db_conn.cursor()
        cursor.execute("SELECT status FROM vacancies WHERE id = 123")
        status = cursor.fetchone()[0]
        assert status == "applied"
