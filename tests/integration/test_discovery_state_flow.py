import pytest
import sqlite3
from core import database

@pytest.fixture
def db_conn():
    """Fixture to set up an in-memory SQLite database for testing."""
    conn = sqlite3.connect(":memory:")
    database.init_db(conn)
    yield conn
    conn.close()


class TestDiscoveryStateIntegration:
    def test_state_crud_and_idempotent_inserts(self, db_conn):
        """
        End-to-end style flow verifying that:
        - discovery_state row is created/updated for a given search_key
        - inserting the same job ids multiple times does not create duplicates
        - watermarks move forward after discovery runs
        """
        search_key = "test_search"

        # 1. Initial state should be None
        assert database.get_discovery_state(search_key, db_conn) is None

        # 2. First discovery run
        database.upsert_discovery_state(search_key, 100, 50, db_conn)
        state = database.get_discovery_state(search_key, db_conn)
        assert state["last_seen_max_job_id"] == 100
        assert state["last_complete_sweep_before_id"] == 50

        # 3. Insert some jobs
        jobs_batch1 = [(1, "A", "B", "C"), (2, "D", "E", "F")]
        database.save_discovered_jobs(jobs_batch1, db_conn)
        assert len(database.get_jobs_to_enrich(db_conn)) == 2

        # 4. Insert another batch with one duplicate
        jobs_batch2 = [(2, "D", "E", "F"), (3, "G", "H", "I")]
        database.save_discovered_jobs(jobs_batch2, db_conn)
        assert len(database.get_jobs_to_enrich(db_conn)) == 3  # Count should increase by 1

        # 5. Second discovery run with new watermarks
        database.upsert_discovery_state(search_key, 110, 40, db_conn)
        state = database.get_discovery_state(search_key, db_conn)
        assert state["last_seen_max_job_id"] == 110  # Should be updated
        assert state["last_complete_sweep_before_id"] == 40  # Should be updated

        # 6. Insert same jobs again (should be ignored)
        database.save_discovered_jobs(jobs_batch1, db_conn)
        assert len(database.get_jobs_to_enrich(db_conn)) == 3  # Count should not change

