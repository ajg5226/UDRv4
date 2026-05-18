# ATLAS Feature Engine

This document describes the implemented feature system in `src/atlas/features`.
It covers the V2 schema, calculation flow, persistence contract, and current
runtime constraints.

## Source of truth

Feature Engine V2 is catalog-driven. The canonical feature definitions live in
`src/atlas/features/schema.py` as `FEATURE_CATALOG`.

The catalog defines:

- Feature identity: `name`, `family`, `description`, `version`.
- Timing: `horizon_family`, `lookback_days`, `min_history`, optional
  `lookback_variants`.
- Interpretation: `directionality`.
- Output variants: requested `transforms`.
- Input needs: `requires`, `depends_on_features`, `universe_scope`.
- Run controls: `enabled` and `priority`.

The repository also contains `config/features/registry.yaml` for the legacy
feature configuration path. Do not add a V2 feature only to that YAML file;
add it to `FEATURE_CATALOG` and implement its calculation in the matching
family generator.

## Feature families and variants

Current V2 catalog size:

| Family | Variant count | Examples |
|--------|---------------|----------|
| `momentum` | 29 | `mom_ts`, `mom_risk_adj`, `mom_residual` |
| `trend` | 21 | `trend_slope`, `trend_adx`, `trend_efficiency` |
| `breakout` | 15 | `breakout_high`, `breakout_dist_high` |
| `mean_reversion` | 16 | `mr_zscore`, `mr_reversal`, `mr_rsi` |
| `factor` | 26 | `factor_beta_spy`, `factor_beta_qual` |
| `risk` | 12 | `risk_realized_vol`, `risk_drawdown` |
| `udr` | 14 | `udr_up_capture`, `udr_down_capture` |
| `regime` | 6 | `regime_hurst`, `regime_corr_spy` |

There are 36 enabled base features and 139 generated variants after lookbacks
and transforms.

Feature names are generated as:

```text
<base_name>_<lookback>d[_<transform>]
```

Examples:

- `mom_ts_21d`
- `mom_ts_21d_rank`
- `risk_realized_vol_63d`
- `factor_beta_spy_126d_rank`

Raw values still include the lookback suffix because the same base definition
can produce multiple horizons.

## Calculation flow

`FeatureEngineV2.calculate()` coordinates the implemented flow:

1. Select enabled features by `FeatureEngineConfig.max_priority` and
   `enabled_families`.
2. Load OHLCV history from `OHLCVRepository.get_as_dataframe()`.
   The load window uses the maximum `min_history` across enabled features plus
   a 30-day buffer.
3. Load optional benchmark data for `SPY` and optional factor ETF data from
   `FACTOR_ETF_CONFIG` when those instruments exist in `dim_instrument`.
4. Route each feature to the generator for its `FeatureFamily`.
5. Calculate raw variants for each requested lookback.
6. Apply panel transforms with `PanelTransformer`.
7. Persist non-null outputs to `fact_feature`.
8. Defer diagnostics that need future returns.

The generator registry is in `src/atlas/features/generators.py`:

```python
GENERATORS = {
    FeatureFamily.MOMENTUM: MomentumGenerator(),
    FeatureFamily.TREND: TrendGenerator(),
    FeatureFamily.BREAKOUT: BreakoutGenerator(),
    FeatureFamily.MEAN_REVERSION: MeanReversionGenerator(),
    FeatureFamily.FACTOR: FactorGenerator(),
    FeatureFamily.RISK: RiskGenerator(),
    FeatureFamily.UDR: UDRGenerator(),
    FeatureFamily.REGIME: RegimeGenerator(),
}
```

## Transforms

`PanelTransformer` applies cross-sectional transforms for one feature on one
date across the instrument universe.

| Transform | Output |
|-----------|--------|
| `raw` | Original calculated value |
| `rank` | Percentile rank from 0 to 100 |
| `zscore` | 2.5% winsorized z-score clipped to +/-3 |
| `quintile` | Bucket 1 to 5 |
| `decile` | Bucket 1 to 10 |

The current catalog primarily requests raw, rank, and z-score outputs. Quintile
and decile support is available in the transformer but is not broadly enabled
in the catalog.

## Persistence contract

Feature outputs are written to `fact_feature` in `src/atlas/storage/models.py`.

Primary key:

- `instrument_id`
- `trade_date`
- `feature_name`

Lineage and version fields:

- `feature_version`
- `params_hash`
- `transform_type`
- `input_vintage`
- `calc_timestamp`
- `run_id`

`FeatureEngineV2` currently sets `feature_version` to `1.0.0`, derives
`params_hash` from the feature name, records `transform_type`, and sets
`calc_timestamp`. `source_id` is optional and is not populated by the engine.

Diagnostics have a storage model, `feature_diagnostic`, and helper classes in
`src/atlas/features/diagnostics.py`. Runtime diagnostics are currently deferred
inside `FeatureEngineV2` because IC and hit-rate metrics require future returns
relative to the calculation date.

## Running the engine

The nightly orchestrator calls `_calculate_features()`, but that method is
currently a placeholder. Until it is wired to `FeatureEngineV2`, `atlas run` and
`atlas backfill` ingest Tiingo/FRED data and skip actual feature calculation
unless the engine is invoked directly.

Example direct invocation after OHLCV data exists:

```python
import asyncio
from datetime import date

from atlas.features.engine_v2 import FeatureEngineConfig, FeatureEngineV2
from atlas.features.schema import FeatureFamily


async def main() -> None:
    engine = FeatureEngineV2(
        FeatureEngineConfig(
            max_priority=1,
            enabled_families=[FeatureFamily.MOMENTUM, FeatureFamily.RISK],
            apply_transforms=True,
            calculate_diagnostics=False,
        )
    )
    result = await engine.calculate(date(2026, 1, 24), run_id=None)
    print(result.records_written, result.errors)


asyncio.run(main())
```

For local validation of the catalog and generators, run:

```bash
python3 scripts/validate_local.py
```

That script validates the schema, feature variant counts, generators, and panel
transforms with synthetic data. It does not fetch live provider data during the
mini pipeline step.

## Adding a V2 feature

1. Add a `FeatureDefinition` in `src/atlas/features/schema.py`.
2. Choose an existing `FeatureFamily` when possible. Add a new family only when
   the calculation path genuinely differs from existing generators.
3. Implement or extend the family generator in
   `src/atlas/features/generators.py`.
4. Add any required benchmark or factor ETF ticker to `BENCHMARK_CONFIG` or
   `FACTOR_ETF_CONFIG`.
5. Validate with `python3 scripts/validate_local.py`.

Constraints:

- The engine expects OHLCV rows with `instrument_id`, `trade_date`, and
  `adj_close`. Some calculations also use `high`, `low`, and `volume`.
- Benchmark-dependent features return missing values if `SPY` is absent from
  `dim_instrument` or lacks sufficient history.
- Factor-dependent features return missing values when required factor ETFs are
  absent from the database.
- Features with `depends_on_features` are declared for lineage, but composite
  dependency execution is not yet fully implemented for every placeholder
  feature.
