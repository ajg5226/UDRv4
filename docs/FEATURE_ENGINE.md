# Feature Engine V2

ATLAS has two feature calculation paths:

- **Feature Engine V2** is the catalog-driven path exported from `atlas.features`.
  It is implemented in `src/atlas/features/schema.py`,
  `generators.py`, `transforms.py`, `diagnostics.py`, and `engine_v2.py`.
- **Legacy feature engine** remains in `src/atlas/features/base.py`,
  `registry.py`, and `engine.py` for compatibility with older `BaseFeature`
  classes and `config/features/registry.yaml`.

The pipeline orchestrator does not currently call Feature Engine V2. In
`PipelineOrchestrator._calculate_features`, feature calculation is still a
placeholder. Use Feature Engine V2 directly when calculating catalog features.

## Architecture

```text
FeatureDefinition catalog
        |
        v
family-specific generator
        |
        v
raw feature Series indexed by instrument_id
        |
        v
PanelTransformer for rank/zscore/quintile/decile variants
        |
        v
FeatureRepository.upsert_batch -> fact_feature
```

### Source of truth

`src/atlas/features/schema.py` defines the canonical feature catalog:

- Feature families: `momentum`, `trend`, `breakout`, `mean_reversion`,
  `factor`, `risk`, `udr`, and `regime`.
- Metadata on every feature: lookback, minimum history, directionality,
  transforms, data requirements, universe scope, priority, and version.
- Benchmark and factor ticker configuration:
  - primary benchmark: `SPY`
  - factor ETFs: `MTUM`, `QUAL`, `USMV`, `VLUE`, `IWM`, and sector ETFs.

At the time of writing, the catalog contains 36 base feature definitions and
139 generated variants after lookback and transform expansion.

### Generators

`src/atlas/features/generators.py` maps each `FeatureFamily` to a
`BaseGenerator` implementation:

| Family | Generator |
| --- | --- |
| `momentum` | `MomentumGenerator` |
| `trend` | `TrendGenerator` |
| `breakout` | `BreakoutGenerator` |
| `mean_reversion` | `MeanReversionGenerator` |
| `factor` | `FactorGenerator` |
| `risk` | `RiskGenerator` |
| `udr` | `UDRGenerator` |
| `regime` | `RegimeGenerator` |

Generators return raw `pandas.Series` values indexed by `instrument_id`.
Transforms are not applied in generators.

### Transforms

`PanelTransformer` applies cross-sectional transforms for one trade date:

- `raw`: unchanged values.
- `rank`: percentile rank up to 100; higher raw values rank higher.
- `zscore`: winsorizes 2.5% tails, standardizes, then clips to +/-3.
- `quintile` / `decile`: quantile buckets where 1 contains the lowest raw
  values.

Transforms require at least two valid instruments. If fewer values are present,
the transformer returns the input values for that transform.

### Persistence

Feature Engine V2 writes to `fact_feature` through
`FeatureRepository.upsert_batch`. The natural key is:

```text
(instrument_id, trade_date, feature_name)
```

Persisted V2 records include:

- `value`
- `feature_version`
- `params_hash`
- `transform_type`
- `calc_timestamp`
- `run_id`, when supplied

Re-running the same feature/date/instrument updates the existing row.

Diagnostics tables and calculators exist, but `FeatureEngineV2` currently
defers diagnostic calculation because forward returns are not available on the
same target date.

## Usage

Feature Engine V2 loads historical OHLCV data from the configured database. It
needs enough history for the enabled catalog features, plus benchmark/factor ETF
rows when features require them.

```python
import asyncio
from datetime import date

from atlas.features import FeatureEngineConfig, FeatureEngineV2, FeatureFamily


async def main() -> None:
    engine = FeatureEngineV2(
        FeatureEngineConfig(
            max_priority=2,
            enabled_families=[FeatureFamily.MOMENTUM, FeatureFamily.RISK],
            apply_transforms=True,
            calculate_diagnostics=False,
        )
    )

    result = await engine.calculate(
        target_date=date(2026, 1, 24),
        instrument_ids=[1, 2, 3],
        run_id=None,
    )

    print(result.features_calculated, result.records_written, result.errors)


asyncio.run(main())
```

The convenience wrapper uses the default configuration:

```python
from atlas.features import calculate_features

result = await calculate_features(date(2026, 1, 24))
```

## Adding a V2 feature

1. **Add the feature definition** in `src/atlas/features/schema.py`.

   ```python
   register_feature(FeatureDefinition(
       name="risk_example",
       family=FeatureFamily.RISK,
       description="Example risk signal",
       horizon_family=HorizonFamily.MEDIUM,
       lookback_days=63,
       min_history=126,
       transforms=[TransformType.RAW, TransformType.RANK],
       requires=[DataRequirement.OHLCV],
       priority=2,
   ))
   ```

2. **Implement calculation logic** in the generator for the feature family in
   `src/atlas/features/generators.py`.

   ```python
   elif feature.name == "risk_example":
       returns = np.diff(np.log(prices))
       results[instrument_id] = returns[-lookback:].mean()
   ```

3. **Add a generator only for a new family.** If the feature introduces a new
   `FeatureFamily`, create a `BaseGenerator` subclass and register it in the
   `GENERATORS` dictionary.

4. **Verify generated names.** The persisted feature name comes from
   `FeatureDefinition.get_full_name()`, so lookbacks and transforms become names
   such as `risk_example_63d` and `risk_example_63d_rank`.

5. **Exercise the engine against representative OHLCV data.** Include benchmark
   `SPY` and any required factor ETF history when using `DataRequirement.BENCHMARK`
   or `DataRequirement.FACTOR_ETFS`.

## Constraints and common pitfalls

- `config/features/registry.yaml` belongs to the legacy `FeatureEngine` path.
  Editing it does not add V2 catalog features.
- `FeatureEngineConfig.max_priority` filters features by priority. The default
  includes priorities 1 through 3.
- `enabled_families=None` expands to every `FeatureFamily`.
- Missing benchmark or factor ETF history causes dependent generators to return
  empty or `NaN` results rather than fetching data on demand.
- Some catalog entries are placeholders in the current generators and return
  `NaN` until their dependency logic is implemented, including
  `factor_tilt_score`, `risk_beta_trend`, `udr_capture_delta`, and
  `regime_vol_level`.
- V2 diagnostics are deferred in `FeatureEngineV2`; do not assume
  `feature_diagnostic` rows are written during normal feature calculation.
- The main `atlas run` and `atlas backfill` CLI flows do not currently execute
  Feature Engine V2 because the orchestrator feature hook is a placeholder.
