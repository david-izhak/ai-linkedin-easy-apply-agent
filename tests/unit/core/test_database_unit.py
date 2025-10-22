import pytest
import datetime
from unittest.mock import patch, MagicMock, ANY

# Adjust the python path to import the module
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from core import database

@pytest.fixture
def mock_db_connection():
    """Fixture to mock the database connection and cursor."""
    with patch('sqlite3.connect') as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor
        yield mock_conn, mock_cursor

class TestDatabaseUnit:

    def test_save_discovered_jobs(self, mock_db_connection):
        mock_conn, mock_cursor = mock_db_connection
        jobs_data = [
            (123, "/link1", "Title 1", "Company 1"),
            (456, "/link2", "Title 2", "Company 2"),
        ]

        database.save_discovered_jobs(jobs_data)

        # Check if the correct SQL command was executed
        mock_cursor.executemany.assert_called_once()
        call_args = mock_cursor.executemany.call_args
        sql_query = call_args[0][0]
        data = call_args[0][1]

        assert "INSERT OR IGNORE INTO vacancies" in sql_query
        assert len(data) == 2
        # Check the structure of the first item
        assert data[0] == (123, "Title 1", "Company 1", "/link1", "discovered", ANY)
        assert isinstance(data[0][5], datetime.datetime)

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_update_job_status(self, mock_db_connection):
        mock_conn, mock_cursor = mock_db_connection
        job_id = 987
        status = "applied"

        database.update_job_status(job_id, status)

        mock_cursor.execute.assert_called_once_with(
            "UPDATE vacancies SET status = ? WHERE id = ?", (status, job_id)
        )
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_save_enrichment_data(self, mock_db_connection):
        mock_conn, mock_cursor = mock_db_connection
        job_id = 111
        details = {
            "description": "Job desc",
            "company_description": "Comp desc",
            "seniority_level": "Senior",
            "employment_type": "Full-time",
            "job_function": "Engineering",
            "industries": "IT",
            "company_overview": "Overview",
            "company_website": "website.com",
            "company_industry": "Tech",
            "company_size": "1000",
        }

        database.save_enrichment_data(job_id, details)

        expected_sql = """
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
    """
        expected_params = (
            "Job desc", "Comp desc", "Senior", "Full-time", "Engineering", "IT",
            "Overview", "website.com", "Tech", "1000", 111
        )

        mock_cursor.execute.assert_called_once_with(ANY, expected_params)
        # Clean up whitespace to make the SQL comparison robust
        actual_sql_cleaned = ' '.join(mock_cursor.execute.call_args[0][0].split())
        expected_sql_cleaned = ' '.join(expected_sql.split())
        assert actual_sql_cleaned == expected_sql_cleaned

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
