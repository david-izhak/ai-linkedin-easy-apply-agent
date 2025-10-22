import pytest


class TestDiscoveryWatermarkUnit:
    def test_collects_exact_limit_of_unseen_when_duplicates_dominate(self):
        """
        Skeleton: Ensure discovery keeps paginating until it accumulates exactly L unseen items
        even if most items on early pages already exist in DB.

        Arrange:
        - Mock page scraper to return pages where 90% ids already in DB.
        - Limit L=10.

        Act:
        - Run discovery loop.

        Assert:
        - Exactly 10 new vacancies prepared for insert.
        - Paginates across multiple pages when needed.
        """
        assert True

    def test_updates_watermarks_after_run(self):
        """
        Skeleton: Validate that last_seen_max_job_id increases monotonically and
        last_complete_sweep_before_id reflects the deepest observed id boundary
        for the run.
        """
        assert True

