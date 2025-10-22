import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from playwright.async_api import Error as PlaywrightError, Page
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from phases.processing import _is_job_suitable, _process_single_job, run_processing_phase


class TestIsJobSuitable:
    
    def test_is_job_suitable_all_criteria_match(self):
        """Test that a job is suitable when all criteria match."""
        from langdetect import detect
        with patch('phases.processing.detect', return_value='english'):
            job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Python developer")
            patterns = {
                "title": MagicMock(),
                "description": MagicMock()
            }
            patterns["title"].search.return_value = True
            patterns["description"].search.return_value = True
            
            with patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["english"]):
                result = _is_job_suitable(job_data, patterns)
            
            assert result is True
            patterns["title"].search.assert_called_once_with("Software Engineer")
            patterns["description"].search.assert_called_once_with("We are looking for a Python developer")
    
    def test_is_job_suitable_title_mismatch(self):
        """Test that a job is not suitable when title doesn't match."""
        from langdetect import detect
        with patch('phases.processing.detect', return_value='english'):
            job_data = (1, "link", "Product Manager", "Company", "We are looking for a Python developer")
            patterns = {
                "title": MagicMock(),
                "description": MagicMock()
            }
            patterns["title"].search.return_value = None  # Title doesn't match
            patterns["description"].search.return_value = True
            
            with patch('config.JOB_DESCRIPTION_LANGUAGES', ["english"]):
                result = _is_job_suitable(job_data, patterns)
            
            assert result is False
    
    def test_is_job_suitable_description_mismatch(self):
        """Test that a job is not suitable when description doesn't match."""
        from langdetect import detect
        with patch('phases.processing.detect', return_value='english'):
            job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Java developer")
            patterns = {
                "title": MagicMock(),
                "description": MagicMock()
            }
            patterns["title"].search.return_value = True
            patterns["description"].search.return_value = None  # Description doesn't match
            
            with patch('config.JOB_DESCRIPTION_LANGUAGES', ["english"]):
                result = _is_job_suitable(job_data, patterns)
            
            assert result is False
    
    def test_is_job_suitable_language_mismatch(self):
        """Test that a job is not suitable when language doesn't match."""
        from langdetect import detect
        with patch('phases.processing.detect', return_value='spanish'):
            job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Python developer")
            patterns = {
                "title": MagicMock(),
                "description": MagicMock()
            }
            patterns["title"].search.return_value = True
            patterns["description"].search.return_value = True
            
            with patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["english"]):
                result = _is_job_suitable(job_data, patterns)
            
            assert result is False
    
    def test_is_job_suitable_language_any(self):
        """Test that a job is suitable when language is 'any'."""
        from langdetect import detect
        with patch('phases.processing.detect', return_value='spanish'):
            job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Python developer")
            patterns = {
                "title": MagicMock(),
                "description": MagicMock()
            }
            patterns["title"].search.return_value = True
            patterns["description"].search.return_value = True
            
            with patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["any"]):
                result = _is_job_suitable(job_data, patterns)
            
            assert result is True


class TestProcessSingleJob:
    
    @pytest.mark.asyncio
    @patch('phases.processing._is_job_suitable', return_value=True)
    @patch('phases.processing.apply_to_job')
    @patch('phases.processing.update_job_status')
    async def test_process_single_job_suitable_and_applied(self, mock_update_job_status,
                                                          mock_apply_to_job,
                                                          mock_is_job_suitable):
        """Test processing a suitable job that gets applied to."""
        mock_context = AsyncMock()
        mock_page = MagicMock(spec=Page)
        mock_page.is_closed = AsyncMock(return_value=False)
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        job_data = (123, "/job1", "Software Engineer", "Company A", "Job description")
        patterns = {"title": MagicMock(), "description": MagicMock()}
        should_submit = True
        config_globals = {}
        
        mock_apply_to_job.return_value = None  # Successful application
        
        result = await _process_single_job(mock_context, job_data, patterns, should_submit, config_globals)
        
        mock_is_job_suitable.assert_called_once_with(job_data, patterns)
        mock_context.new_page.assert_called_once()
        mock_apply_to_job.assert_called_once_with(
            page=mock_page,
            link="/job1",
            config=config_globals,
            should_submit=should_submit
        )
        mock_update_job_status.assert_called_once_with(123, "applied")
        mock_page.close.assert_called_once()
        assert result is True
    
    @pytest.mark.asyncio
    @patch('phases.processing._is_job_suitable', return_value=False)
    @patch('phases.processing.apply_to_job')
    @patch('phases.processing.update_job_status')
    async def test_process_single_job_not_suitable(self, mock_update_job_status, 
                                                  mock_apply_to_job, 
                                                  mock_is_job_suitable):
        """Test processing a job that doesn't match criteria."""
        mock_context = AsyncMock()
        
        job_data = (123, "/job1", "Software Engineer", "Company A", "Job description")
        patterns = {"title": MagicMock(), "description": MagicMock()}
        should_submit = True
        config_globals = {}
        
        result = await _process_single_job(mock_context, job_data, patterns, should_submit, config_globals)
        
        mock_is_job_suitable.assert_called_once_with(job_data, patterns)
        mock_apply_to_job.assert_not_called()
        mock_update_job_status.assert_called_once_with(123, "skipped_filter")
        assert result is False
    
    @pytest.mark.asyncio
    @patch('phases.processing._is_job_suitable', return_value=True)
    @patch('phases.processing.apply_to_job')
    @patch('phases.processing.update_job_status')
    async def test_process_single_job_playwright_error(self, mock_update_job_status,
                                                      mock_apply_to_job,
                                                      mock_is_job_suitable):
        """Test processing a job when a Playwright error occurs."""
        mock_context = AsyncMock()
        mock_page = MagicMock(spec=Page)
        mock_page.is_closed = AsyncMock(return_value=False)
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        job_data = (123, "/job1", "Software Engineer", "Company A", "Job description")
        patterns = {"title": MagicMock(), "description": MagicMock()}
        should_submit = True
        config_globals = {}
        
        mock_apply_to_job.side_effect = PlaywrightError("Page not found")
        
        result = await _process_single_job(mock_context, job_data, patterns, should_submit, config_globals)
        
        mock_is_job_suitable.assert_called_once_with(job_data, patterns)
        mock_context.new_page.assert_called_once()
        mock_apply_to_job.assert_called_once()
        mock_update_job_status.assert_called_once_with(123, "error")
        mock_page.close.assert_called_once()
        assert result is False
    
    @pytest.mark.asyncio
    @patch('phases.processing._is_job_suitable', return_value=True)
    @patch('phases.processing.apply_to_job')
    @patch('phases.processing.update_job_status')
    async def test_process_single_job_general_error(self, mock_update_job_status,
                                                   mock_apply_to_job,
                                                   mock_is_job_suitable):
        """Test processing a job when a general error occurs."""
        mock_context = AsyncMock()
        mock_page = MagicMock(spec=Page)
        mock_page.is_closed = AsyncMock(return_value=False)
        mock_page.close = AsyncMock()
        mock_context.new_page.return_value = mock_page
        
        job_data = (123, "/job1", "Software Engineer", "Company A", "Job description")
        patterns = {"title": MagicMock(), "description": MagicMock()}
        should_submit = True
        config_globals = {}
        
        mock_apply_to_job.side_effect = Exception("Unexpected error")
        
        result = await _process_single_job(mock_context, job_data, patterns, should_submit, config_globals)
        
        mock_is_job_suitable.assert_called_once_with(job_data, patterns)
        mock_context.new_page.assert_called_once()
        mock_apply_to_job.assert_called_once()
        mock_update_job_status.assert_called_once_with(123, "error")
        mock_page.close.assert_called_once()
        assert result is False


class TestRunProcessingPhase:
    
    @pytest.mark.asyncio
    @patch('phases.processing.get_enriched_jobs')
    @patch('phases.processing._process_single_job')
    @patch('phases.processing.wait')
    async def test_run_processing_phase_no_jobs(self, mock_wait, 
                                               mock_process_single_job, 
                                               mock_get_enriched_jobs):
        """Test processing phase when there are no enriched jobs."""
        mock_context = AsyncMock()
        mock_get_enriched_jobs.return_value = []
        
        await run_processing_phase(mock_context, 0, True, {})
        
        mock_get_enriched_jobs.assert_called_once()
        mock_process_single_job.assert_not_called()
        mock_wait.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('phases.processing.get_enriched_jobs')
    @patch('phases.processing._process_single_job')
    @patch('phases.processing.wait')
    async def test_run_processing_phase_daily_limit_reached(self, mock_wait, 
                                                           mock_process_single_job, 
                                                           mock_get_enriched_jobs):
        """Test processing phase when daily limit is reached."""
        mock_context = AsyncMock()
        mock_get_enriched_jobs.return_value = [
            (123, "/job1", "Software Engineer", "Company A", "Job description")
        ]
        
        # Set applications_today_count to MAX_APPLICATIONS_PER_DAY
        from config import MAX_APPLICATIONS_PER_DAY
        
        await run_processing_phase(mock_context, MAX_APPLICATIONS_PER_DAY, True, {})
        
        mock_get_enriched_jobs.assert_called_once()
        mock_process_single_job.assert_not_called()  # Should not process any jobs
        mock_wait.assert_not_called()
    
    @pytest.mark.asyncio
    @patch('phases.processing.get_enriched_jobs')
    @patch('phases.processing._process_single_job')
    @patch('phases.processing.wait')
    async def test_run_processing_phase_all_jobs_processed(self, mock_wait, 
                                                          mock_process_single_job, 
                                                          mock_get_enriched_jobs):
        """Test processing phase when all jobs are processed."""
        mock_context = AsyncMock()
        mock_get_enriched_jobs.return_value = [
            (123, "/job1", "Software Engineer", "Company A", "Job description"),
            (456, "/job2", "Data Scientist", "Company B", "Job description")
        ]
        
        # Mock _process_single_job to return True for first job (applied) and False for second (not applied)
        mock_process_single_job.side_effect = [True, False]
        
        from config import WAIT_BETWEEN_APPLICATIONS
        
        await run_processing_phase(mock_context, 0, True, {})
        
        mock_get_enriched_jobs.assert_called_once()
        assert mock_process_single_job.call_count == 2
        assert mock_wait.call_count == 2
        mock_wait.assert_called_with(WAIT_BETWEEN_APPLICATIONS)