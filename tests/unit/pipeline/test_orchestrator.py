"""Tests for atlas.pipeline.orchestrator."""

from datetime import date, timedelta

import pandas as pd
import pytest

from atlas.pipeline.orchestrator import RunConfig, RunResult, RunStatus, RunType
from atlas.providers.base import ProviderResult


class TestRunConfig:
    def test_defaults_to_previous_business_day(self):
        config = RunConfig()
        assert config.target_date is not None
        assert config.target_date < date.today()
        assert config.target_date.weekday() < 5

    def test_explicit_date(self):
        config = RunConfig(target_date=date(2026, 1, 15))
        assert config.target_date == date(2026, 1, 15)

    def test_defaults(self):
        config = RunConfig()
        assert config.run_type == RunType.MANUAL
        assert config.providers is None
        assert config.instruments is None
        assert config.tags is None
        assert config.skip_features is False
        assert config.parallel is True

    def test_previous_business_day_on_monday(self):
        d = RunConfig._get_previous_business_day()
        assert d.weekday() < 5


class TestRunResult:
    def test_duration_seconds(self):
        from datetime import datetime
        r = RunResult(
            run_id=1, status=RunStatus.SUCCESS, run_date=date(2026, 1, 1),
            start_time=datetime(2026, 1, 1, 0, 0, 0),
            end_time=datetime(2026, 1, 1, 0, 0, 10),
        )
        assert r.duration_seconds == 10.0

    def test_success_property(self):
        from datetime import datetime
        now = datetime.utcnow()
        r_success = RunResult(run_id=1, status=RunStatus.SUCCESS, run_date=date.today(),
                              start_time=now, end_time=now)
        r_fail = RunResult(run_id=2, status=RunStatus.FAILED, run_date=date.today(),
                           start_time=now, end_time=now)
        assert r_success.success is True
        assert r_fail.success is False


class TestDetermineStatus:
    def _make_orchestrator(self):
        from unittest.mock import MagicMock, patch
        with patch("atlas.pipeline.orchestrator.get_settings"), \
             patch("atlas.pipeline.orchestrator.get_database"), \
             patch("atlas.pipeline.orchestrator.get_provider_registry"):
            from atlas.pipeline.orchestrator import PipelineOrchestrator
            return PipelineOrchestrator()

    def test_all_success_no_errors(self):
        orch = self._make_orchestrator()
        results = {
            "p1": ProviderResult(provider_name="p1", fetch_date=date.today(),
                                 data=pd.DataFrame([1]), success=True),
            "p2": ProviderResult(provider_name="p2", fetch_date=date.today(),
                                 data=pd.DataFrame([1]), success=True),
        }
        assert orch._determine_status(results, []) == RunStatus.SUCCESS

    def test_partial_when_one_fails(self):
        orch = self._make_orchestrator()
        results = {
            "p1": ProviderResult(provider_name="p1", fetch_date=date.today(),
                                 data=pd.DataFrame([1]), success=True),
            "p2": ProviderResult(provider_name="p2", fetch_date=date.today(),
                                 data=pd.DataFrame(), success=False),
        }
        assert orch._determine_status(results, []) == RunStatus.PARTIAL

    def test_failed_when_all_fail(self):
        orch = self._make_orchestrator()
        results = {
            "p1": ProviderResult(provider_name="p1", fetch_date=date.today(),
                                 data=pd.DataFrame(), success=False),
        }
        assert orch._determine_status(results, []) == RunStatus.FAILED

    def test_failed_when_empty(self):
        orch = self._make_orchestrator()
        assert orch._determine_status({}, []) == RunStatus.FAILED

    def test_partial_when_success_with_errors(self):
        orch = self._make_orchestrator()
        results = {
            "p1": ProviderResult(provider_name="p1", fetch_date=date.today(),
                                 data=pd.DataFrame([1]), success=True),
        }
        assert orch._determine_status(results, ["some error"]) == RunStatus.PARTIAL


class TestRunType:
    def test_enum_values(self):
        assert RunType.NIGHTLY.value == "nightly"
        assert RunType.BACKFILL.value == "backfill"
        assert RunType.MANUAL.value == "manual"
