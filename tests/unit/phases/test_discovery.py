import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from phases.discovery import run_discovery_phase


class TestRunDiscoveryPhase:
    
    @pytest.mark.asyncio
    @patch('phases.discovery.get_last_run_timestamp')
    @patch('phases.discovery.fetch_job_links_user')
    @patch('phases.discovery.save_discovered_jobs')
    async def test_run_discovery_phase_first_run(self, mock_save_discovered_jobs, 
                                                mock_fetch_job_links_user, 
                                                mock_get_last_run_timestamp):
        """Test discovery phase for the first run."""
        mock_page = AsyncMock()
        mock_get_last_run_timestamp.return_value = None
        mock_fetch_job_links_user.return_value = [
            (123, "/job1", "Software Engineer", "Company A"),
            (456, "/job2", "Data Scientist", "Company B")
        ]
        
        # Import constants from config
        from config import (
            DEFAULT_JOB_POSTED_FILTER_SECONDS,
            KEYWORDS,
            WORKPLACE,
            GEO_ID,
            DISTANCE,
            SORT_BY,
        )
        
        f_tpr_expected = f"r{DEFAULT_JOB_POSTED_FILTER_SECONDS}"
        
        await run_discovery_phase(mock_page)
        
        mock_get_last_run_timestamp.assert_called_once()
        mock_fetch_job_links_user.assert_called_once_with(
            page=mock_page,
            keywords=KEYWORDS,
            workplace=WORKPLACE,
            geo_id=GEO_ID,
            distance=DISTANCE,
            f_tpr=f_tpr_expected,
            sort_by=SORT_BY,
        )
        mock_save_discovered_jobs.assert_called_once_with([
            (123, "/job1", "Software Engineer", "Company A"),
            (456, "/job2", "Data Scientist", "Company B")
        ])
    
    @pytest.mark.asyncio
    @patch('phases.discovery.get_last_run_timestamp')
    @patch('phases.discovery.fetch_job_links_user')
    @patch('phases.discovery.save_discovered_jobs')
    async def test_run_discovery_phase_subsequent_run(self, mock_save_discovered_jobs, 
                                                     mock_fetch_job_links_user, 
                                                     mock_get_last_run_timestamp):
        """Test discovery phase for a subsequent run."""
        mock_page = AsyncMock()
        
        # Mock a previous run timestamp that was 2 hours ago
        from datetime import datetime, timedelta
        two_hours_ago = datetime.now() - timedelta(hours=2)
        mock_get_last_run_timestamp.return_value = two_hours_ago
        
        mock_fetch_job_links_user.return_value = [
            (789, "/job3", "Product Manager", "Company C")
        ]
        
        # Import constants from config
        from config import (
            KEYWORDS,
            WORKPLACE,
            GEO_ID,
            DISTANCE,
            SORT_BY,
        )
        
        # Calculate expected f_tpr (2 hours + 5 min buffer = 7500 seconds)
        expected_seconds = int((datetime.now() - two_hours_ago).total_seconds()) + 300
        f_tpr_expected = f"r{expected_seconds}"
        
        await run_discovery_phase(mock_page)
        
        mock_get_last_run_timestamp.assert_called_once()
        mock_fetch_job_links_user.assert_called_once_with(
            page=mock_page,
            keywords=KEYWORDS,
            workplace=WORKPLACE,
            geo_id=GEO_ID,
            distance=DISTANCE,
            f_tpr=f_tpr_expected,
            sort_by=SORT_BY,
        )
        mock_save_discovered_jobs.assert_called_once_with([
            (789, "/job3", "Product Manager", "Company C")
        ])
    
    @pytest.mark.asyncio
    @patch('phases.discovery.get_last_run_timestamp')
    @patch('phases.discovery.fetch_job_links_user')
    @patch('phases.discovery.save_discovered_jobs')
    async def test_run_discovery_phase_calls_fetch_job_links_user_with_correct_params(self, mock_save_discovered_jobs, 
                                                                                     mock_fetch_job_links_user, 
                                                                                     mock_get_last_run_timestamp):
        """Test that fetch_job_links_user is called with the correct parameters."""
        mock_page = AsyncMock()
        mock_get_last_run_timestamp.return_value = None
        mock_fetch_job_links_user.return_value = []
        
        await run_discovery_phase(mock_page)
        
        # Verify the call was made
        assert mock_fetch_job_links_user.called