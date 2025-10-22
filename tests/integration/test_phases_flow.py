import pytest
from unittest.mock import patch, AsyncMock

# Adjust the python path to import the modules
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from core import database
from phases.discovery import run_discovery_phase
from phases.enrichment import run_enrichment_phase
from phases.processing import run_processing_phase

# This test needs the db_connection fixture.
@pytest.mark.usefixtures("db_connection")
class TestPhasesFlow:

    # This test does NOT use playwright, so it needs @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_full_end_to_end_flow(self):
        """Tests the flow from discovery to processing using a mock database and actions."""
        
        # Using `with patch(...)` is more reliable than decorators for complex cases.
        with patch('phases.discovery.get_last_run_timestamp') as mock_get_last_run, \
             patch('phases.discovery.fetch_job_links_user', new_callable=AsyncMock) as mock_fetch_links, \
             patch('phases.enrichment.fetch_job_details', new_callable=AsyncMock) as mock_fetch_details, \
             patch('phases.processing.apply_to_job', new_callable=AsyncMock) as mock_apply_job, \
             patch('phases.processing.detect') as mock_detect:

            # --- 1. ARRANGE --- 
            mock_get_last_run.return_value = None
            mock_detect.return_value = 'english' # Make langdetect deterministic
            mock_fetch_links.return_value = [
                (999, "/job/999", "Test Software Engineer", "TestCo"),
            ]
            mock_fetch_details.return_value = {
                "description": "Must know Python.",
                "seniority_level": "Entry level"
            }

            mock_page = AsyncMock()
            mock_context = AsyncMock()
            mock_context.new_page.return_value = AsyncMock()

            # --- 2. DISCOVERY PHASE --- 
            await run_discovery_phase(mock_page)

            # Assert discovery was successful
            discovered_jobs = database.get_discovered_jobs()
            assert len(discovered_jobs) == 1
            assert discovered_jobs[0][0] == 999

            # --- 3. ENRICHMENT PHASE ---
            await run_enrichment_phase(mock_context)

            # Assert enrichment was successful
            assert len(database.get_discovered_jobs()) == 0
            enriched_jobs = database.get_enriched_jobs()
            assert len(enriched_jobs) == 1
            assert enriched_jobs[0][0] == 999
            assert enriched_jobs[0][4] == "Must know Python."

            # --- 4. PROCESSING PHASE ---
            with patch('phases.processing.JOB_TITLE', r"software engineer"), \
                 patch('phases.processing.JOB_DESCRIPTION', r"python"), \
                 patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["english"]):
                
                await run_processing_phase(
                    context=mock_context,
                    applications_today_count=0,
                    should_submit=True,
                    config_globals={}
                )

            # Assert processing was successful
            assert len(database.get_enriched_jobs()) == 0
            mock_apply_job.assert_called_once()
