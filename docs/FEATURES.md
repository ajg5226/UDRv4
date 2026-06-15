# Feature Engine

This document describes the feature engine that is implemented in
`src/atlas/features`. It is intentionally scoped to source-code behavior; the
pipeline orchestrator and dashboard integration points are called out separately
because they are not fully wired yet.

## Current implementation status

| Area | Status | Source |
|------|--------|--------|
| Feature catalog | Implemented in Python as the source of truth | `src/atlas/features/schema.py` |
| Family-specific raw calculations | Implemented for momentum, trend, breakout, mean reversion, factor, risk, UDR, and regime families | `src/atlas/features/generators.py` |
| Cross-sectional transforms | Implemented for raw, rank, z-score, quintile, and decile transforms | `src/atlas/features/transforms.py` |
| Feature persistence | Implemented through `FeatureEngineV2` and `FeatureRepository` writes to `fact_feature` | `src/atlas/features/engine_v2.py`, `src/atlas/storage/models.py` |
| Diagnostics models and calculators | Partially implemented; diagnostics are calculated by utility classes, but the engine defers storage during normal calculation because forward returns require future data | `src/atlas/features/diagnostics.py`, `src/atlas/features/engine_v2.py` |
| Pipeline integration | Not complete; `PipelineOrchestrator._calculate_features()` is still a placeholder | `src/atlas/pipeline/orchestrator.py` |
| Dashboard integration | Not complete; the dashboard features tab is a "coming soon" placeholder | `src/atlas/dashboard/app.py` |

Operationally, `atlas run` and `atlas backfill` accept `--skip-features`, but
feature calculation is not currently performed by the orchestrator even when
features are enabled.

## Source of truth

Feature Engine V2 uses `FEATURE_CATALOG` in `src/atlas/features/schema.py`.
Each `FeatureDefinition` describes:

- identity: `name`, `family`, and `description`
- timing: `horizon_family`, `lookback_days`, and `min_history`
- variants: optional `lookback_variants` and `transforms`
- interpretation: `directionality`
- inputs: `requires` and `depends_on_features`
- control metadata: `universe_scope`, `enabled`, `priority`, and `version`

The legacy YAML file at `config/features/registry.yaml` is still present, and
`FeaturesConfig.registry_config` points to it, but `FeatureEngineV2` currently
reads feature definitions from `schema.py`.

## Feature families and naming

Implemented families are:

- `momentum`
- `trend`
- `breakout`
- `mean_reversion`
- `factor`
- `risk`
- `udr`
- `regime`

Feature names are generated from the base name plus optional lookback and
transform suffixes. For example, the base feature:

```python
FeatureDefinition(
    name="mom_ts",
    lookback_variants=[21, 63, 126, 252],
    transforms=[TransformType.RAW, TransformType.RANK, TransformType.ZSCORE],
)
```

produces names such as:

- `mom_ts_21d`
- `mom_ts_21d_rank`
- `mom_ts_21d_zscore`
- `mom_ts_252d`

At the time this guide was written, the catalog contains 36 base definitions
and 139 generated variants. Recount from source when changing the catalog:

```bash
python3 - <<'PY'
import importlib.util

spec = importlib.util.spec_from_file_location(
    "feature_schema",
    "src/atlas/features/schema.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

print(len(module.get_all_features()))
print(len(module.get_all_feature_variants()))
print(module.count_total_features())
PY
```

This import path avoids importing the whole `atlas.features` package, which can
require optional runtime dependencies such as pandas and scipy.

## Calculation flow

`FeatureEngineV2.calculate()` performs the following steps:

1. Select enabled features up to `FeatureEngineConfig.max_priority`.
2. Load OHLCV history back to the maximum `min_history` requirement plus a
   small buffer.
3. Load SPY benchmark data and factor ETF data when those instruments are
   available in the database.
4. Dispatch raw calculations to a family generator returned by
   `get_generator(family)`.
5. Apply requested cross-sectional transforms across the instrument universe.
6. Persist non-null values to `fact_feature` with lineage fields:
   `feature_version`, `params_hash`, `transform_type`, `calc_timestamp`, and
   `run_id`.
7. Defer diagnostics because information-coefficient and hit-rate checks need
   forward returns.

## Adding or changing a V2 feature

1. Add or update the `FeatureDefinition` in `src/atlas/features/schema.py`.
2. If the base name is new, implement calculation logic in the appropriate
   generator in `src/atlas/features/generators.py`.
3. Confirm the selected `requires` values match data that the engine can load:
   - `OHLCV` from `fact_ohlcv`
   - `BENCHMARK` from the configured benchmark ticker (`SPY`)
   - `FACTOR_ETFS` from the configured factor ETF tickers
   - `FEATURES` for future feature-on-feature dependencies
4. Choose transforms intentionally:
   - `rank` returns percentile rank on a 0-100 scale.
   - `zscore` winsorizes tails, standardizes, then clips.
   - `quintile` and `decile` assign bucket numbers.
5. Run focused checks for the catalog and generator behavior.

Example catalog entry:

```python
register_feature(FeatureDefinition(
    name="risk_realized_vol",
    family=FeatureFamily.RISK,
    description="Realized volatility (annualized)",
    horizon_family=HorizonFamily.MULTI,
    lookback_days=21,
    min_history=126,
    lookback_variants=[21, 63],
    directionality=Directionality.LOWER_BETTER,
    transforms=[TransformType.RAW, TransformType.RANK],
    requires=[DataRequirement.OHLCV],
    priority=1,
))
```

## Common pitfalls

- Do not add new V2 features only to `config/features/registry.yaml`; that file
  is not the V2 catalog source.
- Do not assume `atlas run` persists feature rows until orchestrator integration
  is implemented.
- Benchmark and factor features return missing values when SPY or factor ETF
  instruments are not present in the database.
- Diagnostics should be evaluated on a lagged date where forward-return data is
  available.
- Keep table names singular when querying storage models: `fact_feature`,
  `feature_diagnostic`, and `pipeline_run`.
