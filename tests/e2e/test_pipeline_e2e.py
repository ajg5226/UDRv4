"""End-to-end test: full pipeline run with mocked API responses."""

import asyncio
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig, RunType, RunStatus
from atlas.providers.base import ProviderResult, ProviderType
from atlas.storage.models import (
    Base,
    DimInstrument,
    DimMacroSeries,
    DimSource,
    FactMacro,
    FactOHLCV,
    PipelineRun,
)


MOCK_TIINGO_DATA = pd.DataFrame([
    {"ticker": "AAPL", "trade_date": date(2026, 2, 24),
     "open": 267.86, "high": 274.89, "low": 267.71, "close": 272.14,
     "volume": 47014619, "adj_open": 267.86, "adj_high": 274.89,
     "adj_low": 267.71, "adj_close": 272.14, "adj_volume": 47014619,
     "dividend": 0.0, "split_factor": 1.0},
    {"ticker": "SPY", "trade_date": date(2026, 2, 24),
     "open": 681.9, "high": 688.35, "low": 680.0, "close": 687.35,
     "volume": 73798727, "adj_open": 681.9, "adj_high": 688.35,
     "adj_low": 680.0, "adj_close": 687.35, "adj_volume": 73798727,
     "dividend": 0.0, "split_factor": 1.0},
])

MOCK_FRED_DATA = pd.DataFrame([
    {"fred_id": "DFF", "obs_date": date(2026, 2, 24), "value": 3.64},
    {"fred_id": "DGS10", "obs_date": date(2026, 2, 24), "value": 4.25},
    {"fred_id": "VIXCLS", "obs_date": date(2026, 2, 24), "value": 15.3},
])


def _make_mock_tiingo_result():
    return ProviderResult(
        provider_name="tiingo", fetch_date=date(2026, 2, 24),
        data=MOCK_TIINGO_DATA, success=True,
    )


def _make_mock_fred_result():
    return ProviderResult(
        provider_name="fred", fetch_date=date(2026, 2, 24),
        data=MOCK_FRED_DATA, success=True,
    )


@pytest.fixture
def e2e_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def e2e_session_factory(e2e_engine):
    return sessionmaker(bind=e2e_engine, autocommit=False, autoflush=False)


class TestFullPipelineRun:
    @pytest.mark.asyncio
    async def test_single_date_pipeline_run(self, e2e_engine, e2e_session_factory):
        """Run the full pipeline for one date with mocked providers."""

        mock_db = MagicMock()
        mock_db.engine = e2e_engine
        mock_db.session_factory = e2e_session_factory
        mock_db.create_tables = MagicMock()
        mock_db.health_check = MagicMock(return_value=True)

        from contextlib import contextmanager
        @contextmanager
        def _session():
            s = e2e_session_factory()
            try:
                yield s
                s.commit()
            except Exception:
                s.rollback()
                raise
            finally:
                s.close()
        mock_db.session = _session

        mock_tiingo = MagicMock()
        mock_tiingo.name = "tiingo"
        mock_tiingo.provider_type = ProviderType.MARKET_DATA
        mock_tiingo.fetch_data = AsyncMock(return_value=_make_mock_tiingo_result())

        mock_fred = MagicMock()
        mock_fred.name = "fred"
        mock_fred.provider_type = ProviderType.MACRO
        mock_fred.fetch_data = AsyncMock(return_value=_make_mock_fred_result())

        mock_registry = MagicMock()
        mock_registry.get.side_effect = lambda name: {"tiingo": mock_tiingo, "fred": mock_fred}[name]
        mock_registry.has.return_value = True

        mock_fred_provider = MagicMock()
        mock_fred_provider.get_all_series.return_value = [
            {"fred_id": "DFF", "name": "Fed Funds Rate", "category": "liquidity"},
            {"fred_id": "DGS10", "name": "10-Year Treasury", "category": "liquidity"},
            {"fred_id": "VIXCLS", "name": "VIX Index", "category": "risk_appetite"},
        ]

        with patch("atlas.pipeline.orchestrator.get_settings") as mock_settings, \
             patch("atlas.pipeline.orchestrator.get_database", return_value=mock_db), \
             patch("atlas.pipeline.orchestrator.get_provider_registry", return_value=mock_registry), \
             patch("atlas.pipeline.orchestrator.setup_providers", new_callable=AsyncMock), \
             patch("atlas.providers.fred.FredProvider", return_value=mock_fred_provider):

            settings = MagicMock()
            settings.pipeline.default_providers = ["tiingo", "fred"]
            settings.pipeline.parallel_providers = False
            settings.features.enabled = False
            mock_settings.return_value = settings

            orch = PipelineOrchestrator()
            config = RunConfig(
                run_type=RunType.MANUAL,
                target_date=date(2026, 2, 24),
                providers=["tiingo", "fred"],
                skip_features=True,
            )
            result = await orch.run(config)

        assert result.run_id is not None
        assert result.status in (RunStatus.SUCCESS, RunStatus.PARTIAL)
        assert result.records_inserted > 0

        session = e2e_session_factory()
        try:
            runs = list(session.scalars(select(PipelineRun)))
            assert len(runs) == 1
            assert runs[0].status in ("success", "partial")

            instruments = list(session.scalars(select(DimInstrument)))
            tickers = {i.ticker for i in instruments}
            assert "AAPL" in tickers
            assert "SPY" in tickers

            ohlcv = list(session.scalars(select(FactOHLCV)))
            assert len(ohlcv) == 2

            macro_series = list(session.scalars(select(DimMacroSeries)))
            assert len(macro_series) == 3

            macro_data = list(session.scalars(select(FactMacro)))
            assert len(macro_data) == 3

            sources = list(session.scalars(select(DimSource)))
            source_names = {s.name for s in sources}
            assert "tiingo" in source_names
            assert "fred" in source_names
        finally:
            session.close()
