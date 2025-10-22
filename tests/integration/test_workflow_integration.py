import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core import database
from phases.discovery import run_discovery_phase
from phases.enrichment import run_enrichment_phase
from phases.processing import run_processing_phase


# This test needs the db_connection fixture.
@pytest.mark.usefixtures("db_connection")
class TestWorkflowIntegration:

    # This test does NOT use playwright, so it needs @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_full_end_to_end_workflow(self):
        """Tests the complete workflow from discovery to processing using mocked external dependencies."""
        
        # Using `with patch(...)` is more reliable than decorators for complex cases.
        with patch('phases.discovery.get_last_run_timestamp') as mock_get_last_run_timestamp, \
             patch('phases.discovery.fetch_job_links_user', new_callable=AsyncMock) as mock_fetch_job_links_user, \
             patch('phases.enrichment.fetch_job_details', new_callable=AsyncMock) as mock_fetch_job_details, \
             patch('phases.processing.apply_to_job', new_callable=AsyncMock) as mock_apply_to_job, \
             patch('phases.processing.detect') as mock_detect_language:

            # --- 1. ARRANGE --- 
            mock_get_last_run_timestamp.return_value = None
            mock_detect_language.return_value = 'english'  # Make langdetect deterministic
            mock_fetch_job_links_user.return_value = [
                (999, "/job/999", "Test Software Engineer", "TestCo"),
                (998, "/job/998", "Test Data Scientist", "DataCo"),
            ]
            mock_fetch_job_details.return_value = {
                "description": "Must know Python and testing.",
                "seniority_level": "Entry level",
                "company_description": "Great company for testing"
            }

            mock_page = AsyncMock()
            mock_context = AsyncMock()
            mock_context.new_page.return_value = AsyncMock()

            # --- 2. DISCOVERY PHASE --- 
            await run_discovery_phase(mock_page)

            # Assert discovery was successful
            discovered_jobs = database.get_discovered_jobs()
            assert len(discovered_jobs) == 2
            assert {job[0] for job in discovered_jobs} == {99, 98}  # Check job IDs

            # --- 3. ENRICHMENT PHASE ---
            await run_enrichment_phase(mock_context)

            # Assert enrichment was successful
            assert len(database.get_discovered_jobs()) == 0  # No more discovered jobs
            enriched_jobs = database.get_enriched_jobs()
            assert len(enriched_jobs) == 2  # Both jobs are now enriched
            # Check that descriptions were stored
            for job in enriched_jobs:
                assert "Must know Python and testing." in job[4]  # Description is at index 4

            # --- 4. PROCESSING PHASE ---
            with patch('phases.processing.JOB_TITLE', r"software engineer|data scientist"), \
                 patch('phases.processing.JOB_DESCRIPTION', r"python"), \
                 patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["english"]):
                
                await run_processing_phase(
                    context=mock_context,
                    applications_today_count=0,
                    should_submit=True,
                    config_globals={}
                )

            # Assert processing was successful
            # Both jobs should have been processed, and if they matched criteria, applied to
            # The exact assertion depends on the filtering logic in _is_job_suitable
            # Let's check the final statuses in the database
            all_jobs = database.get_enriched_jobs()  # This gets jobs with 'enriched' status
            assert len(all_jobs) == 0  # All jobs should have moved past 'enriched' status
            
            # We can check the database directly for the final status
            # Get all jobs regardless of status to verify the workflow
            conn = database.sqlite3.connect(database.DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT id, status FROM vacancies")
            all_jobs_status = cursor.fetchall()
            conn.close()
            
            # Both jobs should have been processed (either applied or skipped based on filters)
            job_statuses = {job_id: status for job_id, status in all_jobs_status}
            assert 999 in job_statuses
            assert 998 in job_statuses
            # Both jobs match the title filter, and the description filter, so they should be applied to
            # or at least attempted to be applied to (depending on mock behavior of apply_to_job)
            assert mock_apply_to_job.call_count == 2 # Should have tried to apply to both jobs