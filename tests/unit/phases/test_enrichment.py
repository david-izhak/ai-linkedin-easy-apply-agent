import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from playwright.async_api import Error as PlaywrightError, Page # Import Page for spec
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from phases.enrichment import run_enrichment_phase


class TestRunEnrichmentPhase:
    
    @pytest.mark.asyncio
    @patch('phases.enrichment.get_discovered_jobs')
    @patch('phases.enrichment.fetch_job_details')
    @patch('phases.enrichment.save_enrichment_data')
    @patch('phases.enrichment.update_job_status')
    @patch('phases.enrichment.wait')
    async def test_run_enrichment_phase_no_jobs(self, mock_wait, 
                                               mock_update_job_status, 
                                               mock_save_enrichment_data, 
                                               mock_fetch_job_details, 
                                               mock_get_discovered_jobs):
        """Test enrichment phase when there are no discovered jobs."""
        mock_context = AsyncMock()
        mock_get_discovered_jobs.return_value = []
        
        await run_enrichment_phase(mock_context)
        
        mock_get_discovered_jobs.assert_called_once()
        mock_fetch_job_details.assert_not_called()
        mock_save_enrichment_data.assert_not_called()
        mock_update_job_status.assert_not_called()
        mock_wait.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('phases.enrichment.get_discovered_jobs')
    @patch('phases.enrichment.fetch_job_details')
    @patch('phases.enrichment.save_enrichment_data')
    @patch('phases.enrichment.update_job_status')
    @patch('phases.enrichment.wait')
    async def test_run_enrichment_phase_success(self, mock_wait, 
                                               mock_update_job_status, 
                                               mock_save_enrichment_data, 
                                               mock_fetch_job_details, 
                                               mock_get_discovered_jobs):
        """Test enrichment phase with successful processing of jobs."""
        mock_context = AsyncMock()
        mock_page = MagicMock(spec=Page)
        mock_page.is_closed = AsyncMock(return_value=False)
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        mock_get_discovered_jobs.return_value = [
            (123, "/job1", "Software Engineer", "Company A"),
            (456, "/job2", "Data Scientist", "Company B")
        ]
        
        mock_fetch_job_details.return_value = {
            "description": "Job description",
            "company_description": "Company description"
        }
        
        from config import WAIT_BETWEEN_APPLICATIONS
        
        await run_enrichment_phase(mock_context)
        
        mock_get_discovered_jobs.assert_called_once()
        assert mock_fetch_job_details.call_count == 2
        assert mock_save_enrichment_data.call_count == 2
        mock_save_enrichment_data.assert_any_call(123, {
            "description": "Job description",
            "company_description": "Company description"
        })
        mock_save_enrichment_data.assert_any_call(456, {
            "description": "Job description",
            "company_description": "Company description"
        })
        assert mock_page.close.call_count == 2
        assert mock_wait.call_count == 2
        mock_wait.assert_called_with(WAIT_BETWEEN_APPLICATIONS)
    
    @pytest.mark.asyncio
    @patch('phases.enrichment.get_discovered_jobs')
    @patch('phases.enrichment.fetch_job_details')
    @patch('phases.enrichment.save_enrichment_data')
    @patch('phases.enrichment.update_job_status')
    @patch('phases.enrichment.wait')
    async def test_run_enrichment_phase_playwright_error(self, mock_wait, 
                                                        mock_update_job_status, 
                                                        mock_save_enrichment_data, 
                                                        mock_fetch_job_details, 
                                                        mock_get_discovered_jobs):
        """Test enrichment phase when a Playwright error occurs."""
        mock_context = AsyncMock()
        mock_page = MagicMock(spec=Page)
        mock_page.is_closed = AsyncMock(return_value=False)
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        mock_get_discovered_jobs.return_value = [
            (123, "/job1", "Software Engineer", "Company A")
        ]
        
        mock_fetch_job_details.side_effect = PlaywrightError("Page not found")
        
        await run_enrichment_phase(mock_context)
        
        mock_get_discovered_jobs.assert_called_once()
        mock_fetch_job_details.assert_called_once()
        mock_save_enrichment_data.assert_not_called()
        mock_update_job_status.assert_called_once_with(123, "enrichment_error")
        mock_page.close.assert_called_once()
        mock_wait.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('phases.enrichment.get_discovered_jobs')
    @patch('phases.enrichment.fetch_job_details')
    @patch('phases.enrichment.save_enrichment_data')
    @patch('phases.enrichment.update_job_status')
    @patch('phases.enrichment.wait')
    async def test_run_enrichment_phase_general_error(self, mock_wait, 
                                                     mock_update_job_status, 
                                                     mock_save_enrichment_data, 
                                                     mock_fetch_job_details, 
                                                     mock_get_discovered_jobs):
        """Test enrichment phase when a general error occurs."""
        mock_context = AsyncMock()
        mock_page = MagicMock(spec=Page)
        mock_page.is_closed = AsyncMock(return_value=False)
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        mock_get_discovered_jobs.return_value = [
            (123, "/job1", "Software Engineer", "Company A")
        ]
        
        mock_fetch_job_details.side_effect = Exception("Unexpected error")
        
        await run_enrichment_phase(mock_context)
        
        mock_get_discovered_jobs.assert_called_once()
        mock_fetch_job_details.assert_called_once()
        mock_save_enrichment_data.assert_not_called()
        mock_update_job_status.assert_called_once_with(123, "enrichment_error")
        mock_page.close.assert_called_once()
        mock_wait.assert_called_once()