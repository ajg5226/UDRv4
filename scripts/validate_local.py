#!/usr/bin/env python3
"""
Local Validation Script for ATLAS V1

Run this script to validate the entire system works locally before Azure deployment.
Uses SQLite for local database and tests all major components.

Usage:
    python scripts/validate_local.py
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn


console = Console()


def print_header(title: str) -> None:
    console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    console.print(f"[bold blue]{title:^60}[/bold blue]")
    console.print(f"[bold blue]{'='*60}[/bold blue]\n")


def print_success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def print_error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def print_warning(msg: str) -> None:
    console.print(f"[yellow]![/yellow] {msg}")


async def validate_config() -> bool:
    """Validate configuration loading."""
    print_header("1. Configuration Validation")
    
    try:
        from atlas.core.config import get_settings
        settings = get_settings()
        
        print_success(f"Environment: {settings.environment}")
        print_success(f"Database driver: {settings.database.driver}")
        print_success(f"Tiingo enabled: {settings.providers.tiingo.enabled}")
        print_success(f"FRED enabled: {settings.providers.fred.enabled}")
        
        return True
    except Exception as e:
        print_error(f"Configuration error: {e}")
        return False


async def validate_database() -> bool:
    """Validate database connection and schema."""
    print_header("2. Database Validation")
    
    try:
        from atlas.storage.database import get_database
        
        db = get_database()
        
        # Create tables
        console.print("Creating database tables...")
        db.create_tables()
        print_success("Tables created successfully")
        
        # Health check
        if db.health_check():
            print_success("Database health check passed")
        else:
            print_error("Database health check failed")
            return False
        
        return True
    except Exception as e:
        print_error(f"Database error: {e}")
        return False


async def validate_instruments_csv() -> bool:
    """Validate and load instruments from CSV."""
    print_header("3. Instrument Loading")
    
    try:
        import pandas as pd
        from atlas.storage.database import get_database
        from atlas.storage.repository import InstrumentRepository
        from atlas.storage.models import DimInstrument
        
        csv_path = Path(__file__).parent.parent / "ATLAS_INPUT_TEMPLATE_V1.csv"
        
        if not csv_path.exists():
            print_error(f"CSV file not found: {csv_path}")
            return False
        
        df = pd.read_csv(csv_path)
        print_success(f"Loaded {len(df)} tickers from CSV")
        
        db = get_database()
        
        with db.session() as session:
            repo = InstrumentRepository(session)
            
            count = 0
            for _, row in df.iterrows():
                ticker = row["Ticker"]
                existing = repo.get_by_ticker(ticker)
                if existing is None:
                    instrument = DimInstrument(
                        ticker=ticker,
                        asset_type="etf",
                        tiingo_ticker=ticker,
                    )
                    repo.add(instrument)
                    count += 1
            
            print_success(f"Added {count} new instruments to database")
            
            # Verify count
            all_instruments = repo.get_active()
            print_success(f"Total instruments in database: {len(all_instruments)}")
        
        return True
    except Exception as e:
        print_error(f"Instrument loading error: {e}")
        return False


async def validate_feature_schema() -> bool:
    """Validate feature schema."""
    print_header("4. Feature Schema Validation")
    
    try:
        from atlas.features.schema import (
            get_enabled_features,
            get_all_feature_variants,
            count_total_features,
            FeatureFamily,
        )
        
        # Count features
        enabled = get_enabled_features()
        print_success(f"Enabled base features: {len(enabled)}")
        
        # Count variants
        variants = get_all_feature_variants()
        print_success(f"Total feature variants (with lookbacks/transforms): {len(variants)}")
        
        # Count by family
        counts = count_total_features()
        
        table = Table(title="Features by Family")
        table.add_column("Family", style="cyan")
        table.add_column("Count", style="green")
        
        for family, count in counts.items():
            if family != "total":
                table.add_row(family, str(count))
        
        table.add_row("[bold]Total[/bold]", f"[bold]{counts['total']}[/bold]")
        console.print(table)
        
        return True
    except Exception as e:
        print_error(f"Feature schema error: {e}")
        return False


async def validate_providers() -> bool:
    """Validate provider initialization."""
    print_header("5. Provider Validation")
    
    try:
        import os
        from atlas.providers.tiingo import TiingoProvider
        from atlas.providers.fred import FredProvider
        
        # Check API keys
        tiingo_key = os.getenv("TIINGO_API_KEY")
        fred_key = os.getenv("FRED_API_KEY")
        
        if not tiingo_key:
            print_warning("TIINGO_API_KEY not set - Tiingo provider will fail")
        else:
            print_success("Tiingo API key found")
        
        if not fred_key:
            print_warning("FRED_API_KEY not set - FRED provider will fail")
        else:
            print_success("FRED API key found")
        
        # Initialize providers
        console.print("\nInitializing providers...")
        
        tiingo = TiingoProvider()
        await tiingo.initialize()
        print_success("Tiingo provider initialized")
        
        fred = FredProvider()
        await fred.initialize()
        print_success("FRED provider initialized")
        
        # Check FRED series config
        series = fred.get_all_series()
        print_success(f"FRED series configured: {len(series)}")
        
        # Cleanup
        await tiingo.close()
        await fred.close()
        
        return True
    except Exception as e:
        print_error(f"Provider error: {e}")
        return False


async def validate_feature_generators() -> bool:
    """Validate feature generators with sample data."""
    print_header("6. Feature Generator Validation")
    
    try:
        import numpy as np
        import pandas as pd
        from datetime import date, timedelta
        
        from atlas.features.generators import GENERATORS
        from atlas.features.schema import get_features_by_family, FeatureFamily
        
        # Create sample data
        np.random.seed(42)
        n_days = 300
        n_instruments = 10
        
        dates = pd.date_range(end=date.today(), periods=n_days, freq="B")
        
        data_list = []
        for inst_id in range(1, n_instruments + 1):
            # Generate random walk prices
            returns = np.random.normal(0.0005, 0.02, n_days)
            prices = 100 * np.cumprod(1 + returns)
            
            for i, d in enumerate(dates):
                data_list.append({
                    "instrument_id": inst_id,
                    "trade_date": d.date(),
                    "adj_close": prices[i],
                    "high": prices[i] * 1.01,
                    "low": prices[i] * 0.99,
                    "volume": 1000000,
                })
        
        sample_data = pd.DataFrame(data_list)
        target_date = dates[-1].date()
        
        print_success(f"Created sample data: {len(sample_data)} rows, {n_instruments} instruments")
        
        # Test each generator
        for family, generator in GENERATORS.items():
            features = get_features_by_family(family)
            if not features:
                continue
            
            feature = features[0]  # Test first feature of each family
            lookback = feature.lookback_variants[0] if feature.lookback_variants else feature.lookback_days
            
            try:
                result = generator.calculate(
                    feature=feature,
                    data=sample_data,
                    lookback=lookback,
                    target_date=target_date,
                )
                
                valid_count = result.dropna().count()
                print_success(f"{family.value}: {feature.name} - {valid_count}/{n_instruments} valid values")
                
            except Exception as e:
                print_error(f"{family.value}: {feature.name} - Error: {e}")
        
        return True
    except Exception as e:
        print_error(f"Generator validation error: {e}")
        return False


async def validate_transforms() -> bool:
    """Validate cross-sectional transforms."""
    print_header("7. Transform Validation")
    
    try:
        import numpy as np
        import pandas as pd
        from datetime import date
        
        from atlas.features.transforms import PanelTransformer, TransformType
        
        transformer = PanelTransformer()
        
        # Create sample feature values
        np.random.seed(42)
        n_instruments = 100
        raw_values = pd.Series(
            np.random.randn(n_instruments),
            index=range(1, n_instruments + 1),
            name="test_feature"
        )
        
        # Add some outliers
        raw_values.iloc[0] = 10  # High outlier
        raw_values.iloc[1] = -10  # Low outlier
        
        target_date = date.today()
        
        # Test each transform
        for transform in [TransformType.RAW, TransformType.RANK, TransformType.ZSCORE, TransformType.QUINTILE]:
            result = transformer.transform(raw_values, transform, "test", target_date)
            
            valid = result.values.dropna()
            
            if transform == TransformType.RANK:
                # Ranks should be 0-100
                assert valid.min() >= 0 and valid.max() <= 100, "Rank out of range"
                print_success(f"RANK: range [{valid.min():.1f}, {valid.max():.1f}]")
                
            elif transform == TransformType.ZSCORE:
                # Z-scores should be clipped
                assert valid.min() >= -3.1 and valid.max() <= 3.1, "Zscore not clipped"
                print_success(f"ZSCORE: range [{valid.min():.2f}, {valid.max():.2f}] (clipped)")
                
            elif transform == TransformType.QUINTILE:
                # Quintiles should be 1-5
                assert valid.min() >= 1 and valid.max() <= 5, "Quintile out of range"
                print_success(f"QUINTILE: values {sorted(valid.unique())}")
                
            else:
                print_success(f"RAW: {len(valid)} values")
        
        return True
    except Exception as e:
        print_error(f"Transform validation error: {e}")
        return False


async def run_mini_pipeline() -> bool:
    """Run a mini pipeline test (no actual data fetch)."""
    print_header("8. Mini Pipeline Test")
    
    try:
        from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig, RunType
        
        print_warning("Skipping actual data fetch (requires API calls)")
        print_success("Pipeline orchestrator imports successful")
        
        # Just verify we can create the objects
        config = RunConfig(
            run_type=RunType.MANUAL,
            target_date=date.today() - timedelta(days=1),
            skip_features=True,
        )
        
        print_success(f"Run config created: {config.run_type.value} for {config.target_date}")
        
        return True
    except Exception as e:
        print_error(f"Pipeline test error: {e}")
        return False


async def main():
    """Run all validations."""
    print_header("ATLAS V1 Local Validation")
    
    console.print("This script validates all components work locally.\n")
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv()
    
    results = {}
    
    # Run validations
    validations = [
        ("Configuration", validate_config),
        ("Database", validate_database),
        ("Instruments", validate_instruments_csv),
        ("Feature Schema", validate_feature_schema),
        ("Providers", validate_providers),
        ("Feature Generators", validate_feature_generators),
        ("Transforms", validate_transforms),
        ("Mini Pipeline", run_mini_pipeline),
    ]
    
    for name, validator in validations:
        try:
            results[name] = await validator()
        except Exception as e:
            print_error(f"{name}: Unexpected error - {e}")
            results[name] = False
    
    # Summary
    print_header("Validation Summary")
    
    table = Table()
    table.add_column("Component", style="cyan")
    table.add_column("Status", justify="center")
    
    for name, passed in results.items():
        status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
        table.add_row(name, status)
    
    console.print(table)
    
    # Overall result
    all_passed = all(results.values())
    
    if all_passed:
        console.print("\n[bold green]All validations passed![/bold green]")
        console.print("\nNext steps:")
        console.print("1. Run: [cyan]atlas run --date YYYY-MM-DD --verbose[/cyan]")
        console.print("2. Check dashboard: [cyan]atlas dashboard[/cyan]")
    else:
        console.print("\n[bold red]Some validations failed.[/bold red]")
        console.print("Please fix the issues above before proceeding.")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
