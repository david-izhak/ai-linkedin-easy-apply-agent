import re
import pytest
from unittest.mock import patch

# Assuming the file is in D:/py/linkedin-easy-apply-bot/phases/processing.py
# We need to adjust the python path to import it.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')))

from phases.processing import _is_job_suitable


@pytest.fixture
def patterns():
    return {
        "title": re.compile(r"software engineer", re.IGNORECASE),
        "description": re.compile(r"python", re.IGNORECASE),
    }

# Test cases for the _is_job_suitable function
class TestIsJobSuitable:

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["en"])
    def test_matches_all_criteria(self, mock_detect, patterns):
        mock_detect.return_value = 'en'
        job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Python developer.")
        assert _is_job_suitable(job_data, patterns) is True

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["en"])
    def test_mismatched_title(self, mock_detect, patterns):
        mock_detect.return_value = 'en'
        job_data = (1, "link", "Product Manager", "Company", "We are looking for a Python developer.")
        assert _is_job_suitable(job_data, patterns) is False

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["en"])
    def test_mismatched_description(self, mock_detect, patterns):
        mock_detect.return_value = 'en'
        job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Java developer.")
        assert _is_job_suitable(job_data, patterns) is False

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["es"])
    def test_mismatched_language(self, mock_detect, patterns):
        mock_detect.return_value = 'en'
        job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Python developer.")
        assert _is_job_suitable(job_data, patterns) is False

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["any"])
    def test_language_any(self, mock_detect, patterns):
        mock_detect.return_value = 'en'
        job_data = (1, "link", "Software Engineer", "Company", "We are looking for a Python developer.")
        assert _is_job_suitable(job_data, patterns) is True

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["en"])
    def test_empty_description(self, mock_detect, patterns):
        mock_detect.return_value = 'unknown'
        job_data = (1, "link", "Software Engineer", "Company", "")
        assert _is_job_suitable(job_data, patterns) is False

    @patch('phases.processing.detect')
    @patch('phases.processing.JOB_DESCRIPTION_LANGUAGES', ["en", "unknown"])
    def test_empty_description_with_unknown_allowed(self, mock_detect, patterns):
        mock_detect.return_value = 'unknown'
        # This test failed because the description pattern was looking for 'python'.
        # For an empty description, we should use a pattern that matches anything, like the default.
        patterns["description"] = re.compile(r".*", re.IGNORECASE)
        job_data = (1, "link", "Software Engineer", "Company", "")
        assert _is_job_suitable(job_data, patterns) is True
