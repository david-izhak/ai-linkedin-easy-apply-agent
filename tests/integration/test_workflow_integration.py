import pytest
from unittest.mock import AsyncMock, patch
from dataclasses import replace
import sqlite3

from config import config
from core import database
from main import run_phase


@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    database.init_db(conn)
    yield conn
    conn.close()


class TestWorkflowIntegration:
    @pytest.mark.asyncio
    @patch("phases.discovery.run_discovery_phase", new_callable=AsyncMock)
    @patch("phases.enrichment.run_enrichment_phase", new_callable=AsyncMock)
    @patch("phases.processing.run_processing_phase", new_callable=AsyncMock)
    async def test_full_end_to_end_workflow(
        self,
        mock_processing_phase,
        mock_enrichment_phase,
        mock_discovery_phase,
        db_conn,
        app_config,
    ):
        """Tests the complete workflow from discovery to processing via the main run_phase orchestrator."""

        # --- 1. ARRANGE ---
        test_config = app_config.model_copy(
            update={
                "session": app_config.session.model_copy(
                    update={"db_file": None, "db_conn": db_conn}
                )
            }
        )

        # Mock the main run_phase orchestrator to control the flow
        async def run_phase_side_effect(app_config, browser_context, **kwargs):
            if app_config.bot_mode.mode == "discovery":
                mock_discovery_phase(app_config, browser_context)
            elif app_config.bot_mode.mode == "enrichment":
                mock_enrichment_phase(app_config, browser_context)
            elif app_config.bot_mode.mode == "processing":
                mock_processing_phase(app_config, browser_context)

        # --- 2. ACT ---
        # Simulate running each phase through the main orchestrator
        await run_phase("discovery", test_config, AsyncMock())
        await run_phase("enrichment", test_config, AsyncMock())
        await run_phase("processing", test_config, AsyncMock())

        # --- 3. ASSERT ---
        mock_discovery_phase.assert_awaited_once()
        mock_enrichment_phase.assert_awaited_once()
        mock_processing_phase.assert_awaited_once()

        # Check if the correct config was passed to the final phase
        args, kwargs = mock_processing_phase.call_args
        assert kwargs["app_config"].session.db_conn == db_conn
