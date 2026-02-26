"""Tests for atlas.pipeline.backfill."""

from datetime import date

import pytest

from atlas.pipeline.backfill import BackfillConfig, BackfillManager


class TestBackfillConfig:
    def test_valid_config(self):
        config = BackfillConfig(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        assert config.start_date == date(2026, 1, 1)
        assert config.end_date == date(2026, 1, 31)

    def test_invalid_date_range_raises(self):
        with pytest.raises(ValueError, match="start_date must be before"):
            BackfillConfig(start_date=date(2026, 2, 1), end_date=date(2026, 1, 1))

    def test_invalid_resume_from(self):
        with pytest.raises(ValueError, match="resume_from must be within"):
            BackfillConfig(
                start_date=date(2026, 1, 10),
                end_date=date(2026, 1, 20),
                resume_from=date(2026, 1, 5),
            )

    def test_defaults(self):
        config = BackfillConfig(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))
        assert config.batch_size_days == 30
        assert config.skip_weekends is True
        assert config.continue_on_error is True
        assert config.resume_from is None


class TestBackfillManagerDateGeneration:
    def _make_manager(self):
        from unittest.mock import MagicMock
        return BackfillManager(orchestrator=MagicMock())

    def test_generates_weekday_dates(self):
        mgr = self._make_manager()
        config = BackfillConfig(start_date=date(2026, 1, 5), end_date=date(2026, 1, 11))
        dates = mgr._generate_dates(config)
        for d in dates:
            assert d.weekday() < 5
        assert len(dates) == 5

    def test_skips_weekends(self):
        mgr = self._make_manager()
        config = BackfillConfig(start_date=date(2026, 1, 10), end_date=date(2026, 1, 11))
        dates = mgr._generate_dates(config)
        assert len(dates) == 0

    def test_include_weekends_when_disabled(self):
        mgr = self._make_manager()
        config = BackfillConfig(
            start_date=date(2026, 1, 10), end_date=date(2026, 1, 11), skip_weekends=False
        )
        dates = mgr._generate_dates(config)
        assert len(dates) == 2

    def test_resume_from_skips_earlier_dates(self):
        mgr = self._make_manager()
        config = BackfillConfig(
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 9),
            resume_from=date(2026, 1, 8),
        )
        dates = mgr._generate_dates(config)
        assert all(d >= date(2026, 1, 8) for d in dates)


class TestBackfillManagerBatching:
    def _make_manager(self):
        from unittest.mock import MagicMock
        return BackfillManager(orchestrator=MagicMock())

    def test_single_batch(self):
        mgr = self._make_manager()
        dates = [date(2026, 1, d) for d in range(1, 11)]
        batches = mgr._create_batches(dates, batch_size=30)
        assert len(batches) == 1
        assert len(batches[0]) == 10

    def test_multiple_batches(self):
        mgr = self._make_manager()
        dates = [date(2026, 1, d) for d in range(1, 31)]
        batches = mgr._create_batches(dates, batch_size=10)
        assert len(batches) == 3
        assert len(batches[0]) == 10
        assert len(batches[1]) == 10
        assert len(batches[2]) == 10

    def test_partial_last_batch(self):
        mgr = self._make_manager()
        dates = [date(2026, 1, d) for d in range(1, 8)]
        batches = mgr._create_batches(dates, batch_size=5)
        assert len(batches) == 2
        assert len(batches[0]) == 5
        assert len(batches[1]) == 2


class TestEstimateDuration:
    def _make_manager(self):
        from unittest.mock import MagicMock
        return BackfillManager(orchestrator=MagicMock())

    @pytest.mark.asyncio
    async def test_estimate(self):
        mgr = self._make_manager()
        config = BackfillConfig(start_date=date(2026, 1, 5), end_date=date(2026, 1, 9))
        est = await mgr.estimate_duration(config)
        assert est["total_dates"] > 0
        assert est["batches"] >= 1
        assert est["estimated_minutes"] >= 0
