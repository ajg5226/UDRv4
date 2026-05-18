"""Regression tests for critical security and data-integrity bugs."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import atlas.pipeline.orchestrator as orchestrator_module
from atlas.core.exceptions import PipelineError
from atlas.dashboard import auth
from atlas.storage.models import (
    Base,
    DimInstrument,
    DimMacroSeries,
    DimSource,
    FactFeature,
    FactMacro,
    FactOHLCV,
)
from atlas.storage.repository import FeatureRepository, MacroRepository, OHLCVRepository


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _settings(environment: str) -> SimpleNamespace:
    return SimpleNamespace(
        environment=environment,
        dashboard=SimpleNamespace(
            auth=SimpleNamespace(users_secret="atlas-dashboard-users"),
        ),
    )


def _configure_auth(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    secret_value: str | None,
) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(environment))
    monkeypatch.setattr(auth, "get_secret", lambda secret_name: secret_value)


def test_production_without_configured_users_rejects_default_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch, "production", None)

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False
    assert auth.verify_password("analyst", "atlas123") is False


def test_production_with_malformed_users_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch, "production", "{not-json")

    assert auth.get_users() == {}
    assert auth.verify_password("admin", "atlas123") is False


def test_production_accepts_configured_secret_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = {"operator": auth.hash_password("correct-password")}
    _configure_auth(monkeypatch, "production", json.dumps(users))

    assert auth.verify_password("operator", "correct-password") is True
    assert auth.verify_password("operator", "wrong-password") is False
    assert auth.verify_password("admin", "atlas123") is False


def test_development_without_configured_users_allows_default_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_auth(monkeypatch, "development", None)

    assert auth.verify_password("admin", "atlas123") is True
    assert auth.verify_password("analyst", "atlas123") is True


def test_repository_dataframe_readback_preserves_zero_values(session: Session) -> None:
    source = DimSource(name="test", provider_type="market_data")
    instrument = DimInstrument(ticker="ZERO", asset_type="equity")
    series = DimMacroSeries(fred_id="ZERO_RATE", name="Zero Rate", category="liquidity")
    session.add_all([source, instrument, series])
    session.flush()

    target_date = date(2026, 1, 2)
    session.add_all(
        [
            FactOHLCV(
                instrument_id=instrument.instrument_id,
                trade_date=target_date,
                source_id=source.source_id,
                open=Decimal("0"),
                high=Decimal("0"),
                low=Decimal("0"),
                close=Decimal("0"),
                volume=0,
                adj_open=Decimal("0"),
                adj_high=Decimal("0"),
                adj_low=Decimal("0"),
                adj_close=Decimal("0"),
                adj_volume=0,
            ),
            FactMacro(
                series_id=series.series_id,
                obs_date=target_date,
                source_id=source.source_id,
                value=Decimal("0"),
            ),
            FactFeature(
                instrument_id=instrument.instrument_id,
                trade_date=target_date,
                feature_name="zero_feature",
                value=Decimal("0"),
            ),
        ]
    )
    session.flush()

    ohlcv_df = OHLCVRepository(session).get_as_dataframe()
    macro_df = MacroRepository(session).get_as_dataframe()
    feature_df = FeatureRepository(session).get_features_for_date(target_date)

    assert ohlcv_df.loc[0, "open"] == 0.0
    assert ohlcv_df.loc[0, "adj_close"] == 0.0
    assert ohlcv_df.loc[0, "volume"] == 0
    assert macro_df.loc[0, "value"] == 0.0
    assert feature_df.loc[0, "zero_feature"] == 0.0


def test_ohlcv_upsert_does_not_clear_existing_values_with_missing_input(
    session: Session,
) -> None:
    source = DimSource(name="test", provider_type="market_data")
    instrument = DimInstrument(ticker="SAFE", asset_type="equity")
    session.add_all([source, instrument])
    session.flush()

    trade_date = date(2026, 1, 2)
    repo = OHLCVRepository(session)
    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": Decimal("10"),
                "high": Decimal("12"),
                "low": Decimal("9"),
                "close": Decimal("11"),
            }
        ],
        source.source_id,
    )

    repo.upsert_batch(
        [
            {
                "instrument_id": instrument.instrument_id,
                "trade_date": trade_date,
                "open": None,
                "high": float("nan"),
                "low": Decimal("8"),
                "close": Decimal("10"),
            }
        ],
        source.source_id,
    )

    record = repo.get_by_instrument_date(instrument.instrument_id, trade_date)
    assert record is not None
    assert record.open == Decimal("10")
    assert record.high == Decimal("12")
    assert record.low == Decimal("8")
    assert record.close == Decimal("10")


@pytest.mark.asyncio()
async def test_pipeline_early_run_creation_failure_preserves_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingRunRepository:
        def __init__(self, db_session: object) -> None:
            pass

        def create_run(self, **kwargs: object) -> object:
            raise RuntimeError("database unavailable")

    class FakeDatabase:
        @contextmanager
        def session(self) -> Iterator[object]:
            yield object()

    monkeypatch.setattr(orchestrator_module, "PipelineRunRepository", FailingRunRepository)

    orchestrator = orchestrator_module.PipelineOrchestrator.__new__(
        orchestrator_module.PipelineOrchestrator
    )
    orchestrator._initialized = True
    orchestrator._db = FakeDatabase()
    orchestrator._settings = SimpleNamespace(features=SimpleNamespace(enabled=False))
    orchestrator._registry = SimpleNamespace()

    with pytest.raises(PipelineError) as exc_info:
        await orchestrator.run(
            orchestrator_module.RunConfig(
                target_date=date(2026, 1, 2),
                skip_features=True,
            )
        )

    assert exc_info.value.run_id is None
    assert isinstance(exc_info.value.cause, RuntimeError)
    assert "database unavailable" in str(exc_info.value.cause)
