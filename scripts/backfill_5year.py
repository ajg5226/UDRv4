#!/usr/bin/env python3
"""
5-Year Historical Backfill Script for ATLAS V1

Fetches 5 years of daily OHLCV data from Tiingo and macro data from FRED.
Handles rate limiting and saves data incrementally.

Usage:
    python scripts/backfill_5year.py
"""

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from atlas.core.logging import setup_logging
from atlas.providers.fred import FredProvider
from atlas.providers.tiingo import TiingoProvider
from atlas.storage.database import get_database
from atlas.storage.models import DimMacroSeries, DimSource
from atlas.storage.repository import (
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    SourceRepository,
)

load_dotenv()

console = Console()


def coerce_provider_date(value):
    """Normalize provider date values to a date."""
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    return value


async def main():
    console.print("\n[bold blue]ATLAS V1 - 5 Year Historical Backfill[/bold blue]\n")

    setup_logging()

    # Date range
    end_date = date.today() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=5 * 365)  # ~5 years ago

    console.print(f"Date range: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")
    console.print(f"Approximately {(end_date - start_date).days} calendar days\n")

    # Initialize database
    db = get_database()

    # Get instruments
    with db.session() as session:
        inst_repo = InstrumentRepository(session)
        instruments = inst_repo.get_active()
        tickers = [i.ticker for i in instruments]
        ticker_to_id = {i.ticker: i.instrument_id for i in instruments}

    console.print(f"Instruments to fetch: [green]{len(tickers)}[/green]\n")

    # =========================================================================
    # PART 1: Fetch OHLCV data from Tiingo
    # =========================================================================
    console.print("[bold]Part 1: Fetching OHLCV data from Tiingo[/bold]\n")

    tiingo = TiingoProvider()
    await tiingo.initialize()

    # Ensure Tiingo source exists
    with db.session() as session:
        source_repo = SourceRepository(session)
        tiingo_source = source_repo.get_by_name("tiingo")
        if tiingo_source is None:
            tiingo_source = DimSource(
                name="tiingo",
                provider_type="market_data",
                base_url="https://api.tiingo.com",
            )
            source_repo.add(tiingo_source)
        tiingo_source_id = tiingo_source.source_id

    ohlcv_records = []
    failed_tickers = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching OHLCV...", total=len(tickers))

        for ticker in tickers:
            try:
                df = await tiingo.fetch_date_range(
                    ticker=ticker,
                    start_date=start_date,
                    end_date=end_date,
                )

                instrument_id = ticker_to_id.get(ticker)

                if instrument_id and not df.empty:
                    for _, row in df.iterrows():
                        # The Tiingo provider returns 'trade_date', not 'date'
                        trade_date = row.get("trade_date", row.get("date"))
                        trade_date = coerce_provider_date(trade_date)
                        if trade_date is not None:
                            ohlcv_records.append(
                                {
                                    "instrument_id": instrument_id,
                                    "trade_date": trade_date,
                                    # Raw prices
                                    "open": row.get("open"),
                                    "high": row.get("high"),
                                    "low": row.get("low"),
                                    "close": row.get("close"),
                                    "volume": row.get("volume"),
                                    # Adjusted prices
                                    "adj_open": row.get("adj_open"),
                                    "adj_high": row.get("adj_high"),
                                    "adj_low": row.get("adj_low"),
                                    "adj_close": row.get("adj_close"),
                                    "adj_volume": row.get("adj_volume"),
                                    # Corporate actions
                                    "dividend": row.get("dividend"),
                                    "split_factor": row.get("split_factor"),
                                }
                            )
                elif df.empty:
                    failed_tickers.append(ticker)

            except Exception as e:
                failed_tickers.append(ticker)
                console.print(f"[red]Error fetching {ticker}: {e}[/red]")

            progress.advance(task)

            # Small delay to respect rate limits
            await asyncio.sleep(0.15)

    await tiingo.close()

    console.print(
        f"\n[green]Fetched {len(ohlcv_records):,} OHLCV records from {len(tickers) - len(failed_tickers)} tickers[/green]"
    )
    if failed_tickers:
        console.print(
            f"[yellow]Failed/empty tickers ({len(failed_tickers)}): {', '.join(failed_tickers[:15])}{'...' if len(failed_tickers) > 15 else ''}[/yellow]"
        )

    # Save OHLCV to database
    if ohlcv_records:
        console.print("\nSaving OHLCV data to database...")
        with db.session() as session:
            ohlcv_repo = OHLCVRepository(session)
            inserted, updated = ohlcv_repo.upsert_batch(ohlcv_records, source_id=tiingo_source_id)
            console.print(f"[green]Saved: {inserted:,} inserted, {updated:,} updated[/green]")

    # =========================================================================
    # PART 2: Fetch Macro data from FRED
    # =========================================================================
    console.print("\n[bold]Part 2: Fetching Macro data from FRED[/bold]\n")

    fred = FredProvider()
    await fred.initialize()

    # Ensure FRED source exists
    with db.session() as session:
        source_repo = SourceRepository(session)
        fred_source = source_repo.get_by_name("fred")
        if fred_source is None:
            fred_source = DimSource(
                name="fred",
                provider_type="macro_data",
                base_url="https://api.stlouisfed.org",
            )
            source_repo.add(fred_source)
        fred_source_id = fred_source.source_id

    # Get all FRED series
    fred_series = fred.get_all_series()
    console.print(f"FRED series to fetch: [green]{len(fred_series)}[/green]\n")

    macro_records = []
    failed_series = []

    # Create/get macro series in database
    series_to_id = {}
    with db.session() as session:
        series_repo = MacroSeriesRepository(session)

        for series_info in fred_series:
            fred_id = series_info["fred_id"]  # FRED provider uses 'fred_id' key
            existing = series_repo.get_by_fred_id(fred_id)

            if existing is None:
                new_series = DimMacroSeries(
                    fred_id=fred_id,
                    name=series_info.get("name", fred_id),
                    frequency=series_info.get("frequency", "daily"),
                    category=series_info.get("category", "other"),
                )
                series_repo.add(new_series)
                series_to_id[fred_id] = new_series.series_id
            else:
                series_to_id[fred_id] = existing.series_id

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching Macro...", total=len(fred_series))

        for series_info in fred_series:
            fred_id = series_info["fred_id"]  # FRED provider uses 'fred_id' key

            try:
                df = await fred.fetch_date_range(
                    series_id=fred_id,
                    start_date=start_date,
                    end_date=end_date,
                )

                db_series_id = series_to_id.get(fred_id)

                if db_series_id and not df.empty:
                    for _, row in df.iterrows():
                        if row.get("value") is not None:
                            obs_date = row.get("obs_date", row.get("date"))
                            obs_date = coerce_provider_date(obs_date)
                            if obs_date is not None:
                                macro_records.append(
                                    {
                                        "series_id": db_series_id,
                                        "source_id": fred_source_id,
                                        "obs_date": obs_date,
                                        "value": row["value"],
                                    }
                                )
                elif df.empty:
                    failed_series.append(fred_id)

            except Exception as e:
                failed_series.append(fred_id)
                console.print(f"[red]Error fetching {fred_id}: {e}[/red]")

            progress.advance(task)

            # FRED rate limit is generous but let's be nice
            await asyncio.sleep(0.25)

    await fred.close()

    console.print(f"\n[green]Fetched {len(macro_records):,} macro records[/green]")
    if failed_series:
        console.print(
            f"[yellow]Failed series ({len(failed_series)}): {', '.join(failed_series[:10])}{'...' if len(failed_series) > 10 else ''}[/yellow]"
        )

    # Save Macro to database
    if macro_records:
        console.print("\nSaving Macro data to database...")
        with db.session() as session:
            macro_repo = MacroRepository(session)
            inserted, updated = macro_repo.upsert_batch(macro_records, source_id=fred_source_id)
            console.print(f"[green]Saved: {inserted:,} inserted, {updated:,} updated[/green]")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    console.print("\n" + "=" * 60)
    console.print("[bold green]Backfill Complete![/bold green]")
    console.print("=" * 60 + "\n")

    table = Table(title="Data Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Date Range", f"{start_date} to {end_date}")
    table.add_row("OHLCV Records", f"{len(ohlcv_records):,}")
    table.add_row("Tickers Fetched", f"{len(tickers) - len(failed_tickers)}/{len(tickers)}")
    table.add_row("Macro Records", f"{len(macro_records):,}")
    table.add_row(
        "FRED Series Fetched", f"{len(fred_series) - len(failed_series)}/{len(fred_series)}"
    )

    console.print(table)

    console.print("\nNext steps:")
    console.print(
        "1. Calculate features: [cyan]PYTHONPATH=src python3 -c 'from atlas.features import ...'[/cyan]"
    )
    console.print(
        "2. Launch dashboard: [cyan]PYTHONPATH=src streamlit run src/atlas/dashboard/app.py[/cyan]"
    )


if __name__ == "__main__":
    asyncio.run(main())
