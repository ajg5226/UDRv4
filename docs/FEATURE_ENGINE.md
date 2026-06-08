# Feature Engine V2

Feature Engine V2 is the schema-driven feature calculation path exported by
`atlas.features`. It defines a feature catalog in Python, maps each feature
family to a generator, optionally creates cross-sectional transforms, and
persists feature values with versioning metadata.

The engine can be used directly today. It is not yet wired into the nightly
pipeline orchestrator: `PipelineOrchestrator._calculate_features()` currently
logs a placeholder and returns without invoking `FeatureEngineV2`.

## Source of truth

| Concern | Source |
|---------|--------|
| Feature definitions and metadata | `src/atlas/features/schema.py` |
| Family-specific calculations | `src/atlas/features/generators.py` |
| Cross-sectional transforms | `src/atlas/features/transforms.py` |
| Engine orchestration and persistence | `src/atlas/features/engine_v2.py` |
| Feature and diagnostic tables | `src/atlas/storage/models.py` |

`FEATURE_CATALOG` in `schema.py` is the canonical V2 catalog. The legacy
`config/features/registry.yaml`, `BaseFeature`, `FeatureRegistry`, and
`FeatureEngine` modules remain in the repository for compatibility, but V2 does
not load feature definitions from YAML.

## How calculation works

1. `FeatureEngineV2.calculate()` selects enabled catalog entries up to
   `FeatureEngineConfig.max_priority`.
2. The engine loads OHLCV history through `OHLCVRepository.get_as_dataframe()`.
   The lookback window is based on the largest enabled feature `min_history`,
   plus a 30-day buffer.
3. Benchmark data is loaded for `BENCHMARK_CONFIG["primary"]` (`SPY`).
4. Factor ETF history is loaded for tickers in `FACTOR_ETF_CONFIG`.
5. Each feature family is delegated to its registered generator in `GENERATORS`:
   momentum, trend, breakout, mean reversion, factor, risk, UDR, or regime.
6. Raw outputs are transformed when requested by the feature definition:
   `rank`, `zscore`, `quintile`, and `decile`.
7. Values are written through `FeatureRepository.upsert_batch()` into
   `fact_feature`.

## Feature naming

Each `FeatureDefinition` can generate variants from lookback windows and
transform types. The naming convention is:

```text
{feature_name}_{lookback}d[_{transform}]
```

Examples:

| Definition | Variant |
|------------|---------|
| `mom_ts` with 21-day lookback, raw transform | `mom_ts_21d` |
| `mom_ts` with 63-day lookback, rank transform | `mom_ts_63d_rank` |
| `trend_slope` with 126-day lookback, z-score transform | `trend_slope_126d_zscore` |

Raw variants omit the `_raw` suffix. Transformed variants append the transform
name. Z-score transforms winsorize the 2.5% tails before standardizing and clip
scores to +/-3 by default.

## Standalone usage

Run V2 directly from Python when you need to calculate features outside the
nightly pipeline:

```python
import asyncio
from datetime import date

from atlas.features import FeatureEngineConfig, FeatureEngineV2, FeatureFamily


async def main() -> None:
    config = FeatureEngineConfig(
        max_priority=1,
        enabled_families=[FeatureFamily.MOMENTUM, FeatureFamily.TREND],
        apply_transforms=True,
        calculate_diagnostics=False,
    )
    engine = FeatureEngineV2(config)
    result = await engine.calculate(
        target_date=date(2026, 1, 24),
        instrument_ids=None,  # None means all active instruments with OHLCV history.
        run_id=None,
    )
    print(result.success, result.features_calculated, result.records_written)


asyncio.run(main())
```

For the default configuration, the convenience wrapper is equivalent:

```python
from datetime import date
from atlas.features import calculate_features

result = await calculate_features(target_date=date(2026, 1, 24), run_id=1)
```

## Adding or changing a V2 feature

1. Add or edit a `FeatureDefinition` in `src/atlas/features/schema.py`.
2. Choose the correct `FeatureFamily`, `HorizonFamily`, `lookback_days`,
   `min_history`, `lookback_variants`, `transforms`, and data requirements.
3. Implement the raw calculation in the matching family generator in
   `src/atlas/features/generators.py` if that generator does not already handle
   the feature name.
4. If the feature depends on benchmark or factor ETF history, confirm the
   required tickers are present as instruments and have OHLCV records.
5. Validate locally with the feature checks in `scripts/validate_local.py`.

Do not add V2 features to `config/features/registry.yaml`; that file belongs to
the legacy feature path.

## Data prerequisites and constraints

- Feature calculation needs enough historical OHLCV records to satisfy each
  feature's `min_history`.
- Benchmark-dependent features require `SPY` in `dim_instrument` with matching
  OHLCV history.
- Factor-dependent features require the configured factor ETF tickers, such as
  `MTUM`, `QUAL`, `USMV`, `VLUE`, and sector ETFs, with OHLCV history.
- Missing factor ETFs are skipped by `_load_factor_data()`. A generator may
  then return empty or missing values for features that need those inputs.
- `FeatureEngineConfig.apply_transforms=False` disables cross-sectional
  transformed variants.
- `FeatureEngineConfig.calculate_diagnostics=True` is accepted, but diagnostic
  persistence is currently deferred in `_calculate_and_store_diagnostics()`
  because diagnostics need future returns.

## Current integration status

| Workflow | Status |
|----------|--------|
| Direct `FeatureEngineV2.calculate()` usage | Implemented |
| `atlas.features.calculate_features()` wrapper | Implemented |
| Persistence to `fact_feature` | Implemented |
| Cross-sectional transforms | Implemented |
| Diagnostics table and calculator scaffolding | Implemented |
| Diagnostics called by engine | Deferred |
| Nightly `atlas run` / `atlas backfill` feature step | Placeholder only |

The CLI accepts `--skip-features` for `atlas run` and `atlas backfill`, but the
non-skipped path currently reaches the orchestrator placeholder rather than V2.
Until the orchestrator calls `FeatureEngineV2`, use the standalone interface for
feature calculation.
