import pytest
from unittest.mock import AsyncMock, patch
from dataclasses import replace

from phases.discovery import (
    run_discovery_phase,
    MIN_RECOMMENDED_PERIOD,
    MAX_RECOMMENDED_PERIOD,
)
from config import config
from pydantic import ValidationError
from config import JobSearchConfig


class TestRunDiscoveryPhase:
    @pytest.mark.asyncio
    @patch("phases.discovery.fetch_job_links_user", new_callable=AsyncMock)
    async def test_run_discovery_phase_uses_config_period(self, mock_fetch, app_config):
        """Test that discovery phase uses the period from the provided config."""
        test_config = app_config.model_copy(
            update={
                "job_search": app_config.job_search.model_copy(
                    update={"job_search_period_seconds": 12345}
                )
            }
        )

        await run_discovery_phase(test_config, AsyncMock())

        mock_fetch.assert_awaited_once()
        # Check that the config's value was passed to the fetch function
        assert mock_fetch.call_args.kwargs["app_config"].job_search.job_search_period_seconds == 12345


class TestDiscoveryPeriodValidation:
    @pytest.mark.asyncio
    async def test_validation_error_on_zero_period(self, app_config):
        """Test that zero period raises ValueError."""
        test_config = app_config.model_copy(
            update={
                "job_search": app_config.job_search.model_copy(
                    update={"job_search_period_seconds": 0}
                )
            }
        )
        with pytest.raises(ValueError, match="JOB_SEARCH_PERIOD_SECONDS must be a positive integer"):
            await run_discovery_phase(test_config, AsyncMock())

    @pytest.mark.asyncio
    async def test_validation_error_on_negative_period(self, app_config):
        """Test that negative period raises ValueError."""
        test_config = app_config.model_copy(
            update={
                "job_search": app_config.job_search.model_copy(
                    update={"job_search_period_seconds": -1}
                )
            }
        )
        with pytest.raises(ValueError, match="JOB_SEARCH_PERIOD_SECONDS must be a positive integer"):
            await run_discovery_phase(test_config, AsyncMock())

    @pytest.mark.asyncio
    async def test_validation_error_on_wrong_type(self, app_config):
        """Test that non-integer period raises TypeError."""
        with pytest.raises(ValidationError):
            JobSearchConfig(job_search_period_seconds="invalid")


class TestDiscoveryPeriodWarnings:
    @pytest.mark.asyncio
    @patch("phases.discovery.fetch_job_links_user", new_callable=AsyncMock)
    async def test_large_period_warning(self, mock_fetch, caplog, app_config):
        """Test that a very large period logs a warning."""
        large_period = MAX_RECOMMENDED_PERIOD + 1
        test_config = app_config.model_copy(
            update={
                "job_search": app_config.job_search.model_copy(
                    update={"job_search_period_seconds": large_period}
                )
            }
        )
        await run_discovery_phase(test_config, AsyncMock())
        assert "larger than recommended" in caplog.text

    @pytest.mark.asyncio
    @patch("phases.discovery.fetch_job_links_user", new_callable=AsyncMock)
    async def test_small_period_warning(self, mock_fetch, caplog, app_config):
        """Test that a very small period logs a warning."""
        small_period = MIN_RECOMMENDED_PERIOD - 1
        test_config = app_config.model_copy(
            update={
                "job_search": app_config.job_search.model_copy(
                    update={"job_search_period_seconds": small_period}
                )
            }
        )
        await run_discovery_phase(test_config, AsyncMock())
        assert "which is very short" in caplog.text
