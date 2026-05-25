# Feature Engine

This document describes the feature system implemented under `src/atlas/features/`.
It is the source-backed reference for adding or operating engineered features in
the current codebase.

## Current status

- Feature definitions live in `src/atlas/features/schema.py`.
- `FeatureEngineV2` in `src/atlas/features/engine_v2.py` can load OHLCV history,
  calculate raw features, apply panel transforms, write `fact_feature`, and write
  diagnostics to `feature_diagnostic`.
- The nightly pipeline does not yet call `FeatureEngineV2`: `PipelineOrchestrator`
  still logs a feature-calculation placeholder in `_calculate_features`.
- `config/features/registry.yaml` describes a legacy feature list. It is loaded
  into settings as a path but is not parsed by the V2 catalog.

Use `atlas run --skip-features` or `atlas backfill --skip-features` when you want
to make this current pipeline behavior explicit during local runs.

## Architecture

```
FEATURE_CATALOG (schema.py)
        |
        v
FeatureEngineV2
        |
        +-- generators.py     family-specific raw calculations
        +-- transforms.py     cross-sectional rank/zscore/buckets
        +-- diagnostics.py    IC, hit-rate, and stability metrics
        |
        v
storage models: fact_feature, feature_diagnostic
```

### Catalog contract

Every V2 feature is a `FeatureDefinition` with:

- `name`, `family`, and `description`
- `lookback_days`, optional `lookback_variants`, and `min_history`
- `directionality` for signal interpretation
- `transforms` to emit, such as `raw`, `rank`, `zscore`, `quintile`, or `decile`
- `requires` data dependencies, such as OHLCV, benchmark, factor ETFs, macro, or
  other features
- `priority`, `enabled`, `version`, and `universe_scope`

`FeatureDefinition.generate_variants()` combines lookbacks and transforms into
the persisted feature names. For example, `udr_up_capture` with 63- and 126-day
lookbacks and raw/rank transforms emits names such as:

```text
udr_up_capture_63d
udr_up_capture_63d_rank
udr_up_capture_126d
udr_up_capture_126d_rank
```

As of this documentation pass, the enabled catalog generates 139 feature
variants across these families:

| Family | Examples | Notes |
|--------|----------|-------|
| `momentum` | `mom_ts`, `mom_risk_adj`, `mom_residual` | Time-series and risk-adjusted momentum. |
| `trend` | `trend_slope`, `trend_adx`, `trend_choppiness` | Trend strength and path quality. |
| `breakout` | `breakout_high`, `breakout_volume_confirm` | Price and volume breakout signals. |
| `mean_reversion` | `mr_rsi`, `mr_bollinger_z` | Overbought/oversold signals. |
| `factor` | `factor_beta_mom`, `factor_residual_sector` | Factor and sector-relative signals. |
| `risk` | `risk_realized_vol`, `risk_drawdown` | Volatility and drawdown features. |
| `udr` | `udr_up_capture`, `udr_down_capture`, `udr_capture_asymmetry` | Up/down capture against the benchmark. |
| `regime` | `regime_hurst`, `regime_corr_spy` | Market regime descriptors. |

Benchmark and factor inputs are configured in `schema.py`:

- primary benchmark: `SPY`
- secondary benchmark placeholder: `AGG`
- factor ETFs include `MTUM`, `QUAL`, `USMV`, `VLUE`, `IWM`, and sector ETFs

## Engine flow

`FeatureEngineV2.calculate(target_date, instrument_ids=None, run_id=None)`:

1. Selects enabled features up to `FeatureEngineConfig.max_priority`.
2. Loads enough OHLCV history for the maximum required `min_history`.
3. Loads benchmark and factor ETF histories for features that need them.
4. Runs the appropriate generator for each feature family.
5. Applies requested cross-sectional transforms.
6. Persists values to `fact_feature` with versioning and lineage fields.
7. Optionally calculates diagnostics for configured forward horizons.

The default `FeatureEngineConfig` enables all families, applies transforms,
calculates diagnostics, and uses priority `<= 3`.

## Panel transforms

`PanelTransformer` transforms one feature across the instrument universe for one
date:

- `raw`: original values
- `rank`: percentile rank from 0 to 100
- `zscore`: winsorized at 2.5% tails, standardized, then clipped to +/-3
- `quintile`: bucket assignment 1 through 5
- `decile`: bucket assignment 1 through 10

Transforms require at least two non-null values; otherwise the input series is
returned unchanged.

## Diagnostics

`DiagnosticsCalculator` computes feature quality metrics against forward
returns. Default horizons are 5, 21, 63, and 126 days.

Persisted diagnostic fields include:

- Spearman and Pearson information coefficients
- hit rate
- t-statistic
- observation count
- universe scope and regime label

Diagnostics are written to `feature_diagnostic`.

## Storage contract

Feature values are stored in `fact_feature` with primary key:

```text
instrument_id, trade_date, feature_name
```

Important lineage fields:

- `feature_version`
- `params_hash`
- `transform_type`
- `input_vintage`
- `calc_timestamp`
- `run_id`

Diagnostic rows are stored in `feature_diagnostic` and indexed by feature/date,
forward horizon, and regime.

## Adding a V2 feature

1. Add or update a `FeatureDefinition` in `src/atlas/features/schema.py`.
2. Ensure the feature family has a generator in `src/atlas/features/generators.py`.
3. Implement the calculation branch for the new feature name.
4. Choose transforms and directionality deliberately; diagnostics depend on this
   interpretation.
5. Run the local validation script:

```bash
python3 scripts/validate_local.py
```

If the feature needs a new family, add a `FeatureFamily` enum value, implement a
new `BaseGenerator`, and register it in the `GENERATORS` map.

## Common pitfalls

- Do not add new V2 features only to `config/features/registry.yaml`; the V2
  engine reads `FEATURE_CATALOG`.
- Keep `min_history` large enough for the generator implementation. The engine
  loads history based on the largest configured `min_history`.
- Features that require benchmark or factor ETF data will produce sparse or null
  outputs if those instruments are absent from `dim_instrument` or lack OHLCV
  history.
- The pipeline feature stage is not wired yet, so successful `atlas run` output
  should not be interpreted as proof that V2 features were calculated.
