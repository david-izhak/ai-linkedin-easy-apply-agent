import pytest
import sqlite3
import datetime

# Adjust the python path to import the module
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core import database

# The db_connection fixture from conftest.py is used automatically
class TestDatabaseFlow:

    def test_happy_path_job_lifecycle(self, db_connection):
        """Tests the complete lifecycle of a job entry in the database."""
        # 1. Save discovered jobs
        discovered_jobs = [
            (123, "/link1", "Software Engineer", "Tech Corp"),
            (456, "/link2", "Data Analyst", "Data Inc."),
        ]
        database.save_discovered_jobs(discovered_jobs)

        # 2. Get discovered jobs and verify
        retrieved_discovered = database.get_discovered_jobs()
        assert len(retrieved_discovered) == 2
        assert retrieved_discovered[0][0] == 456 # job_id
        assert retrieved_discovered[1][0] == 123

        # 3. Save enrichment data for one job
        enrichment_details = {"description": "A great job.", "seniority_level": "Senior"}
        database.save_enrichment_data(123, enrichment_details)

        # 4. Get enriched jobs and verify
        retrieved_enriched = database.get_enriched_jobs()
        assert len(retrieved_enriched) == 1
        assert retrieved_enriched[0][0] == 123 # job_id
        assert retrieved_enriched[0][4] == "A great job." # description

        # 5. Update job status to 'applied'
        database.update_job_status(123, "applied")

        # 6. Verify the job is no longer in the 'enriched' list
        assert len(database.get_enriched_jobs()) == 0

        # 7. Count today's applications
        # The created_at for job 123 was set when save_discovered_jobs was called.
        # Assuming the test runs on the same day, count_todays_applications should find it.
        assert database.count_todays_applications() == 1
