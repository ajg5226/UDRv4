"""Main CLI entry point for ATLAS."""

import asyncio
from datetime import date, datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from atlas.core.config import get_settings
from atlas.core.logging import setup_logging

app = typer.Typer(
    name="atlas",
    help="ATLAS V1 - Nightly Data Pipeline for Investment Management",
    add_completion=False,
)

console = Console()


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse a date string in YYYY-MM-DD format."""
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise typer.BadParameter(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


@app.command()
def run(
    target_date: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Target date (YYYY-MM-DD). Defaults to previous business day.",
    ),
    providers: Optional[str] = typer.Option(
        None, "--providers", "-p",
        help="Comma-separated list of providers to run.",
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", "-t",
        help="Comma-separated list of instrument tags to filter.",
    ),
    skip_features: bool = typer.Option(
        False, "--skip-features",
        help="Skip feature calculation.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging.",
    ),
) -> None:
    """Run the pipeline for a specific date."""
    setup_logging(level="DEBUG" if verbose else "INFO", format_type="text")
    
    from atlas.pipeline.orchestrator import PipelineOrchestrator, RunConfig, RunType
    
    parsed_date = parse_date(target_date)
    provider_list = providers.split(",") if providers else None
    tag_list = tags.split(",") if tags else None
    
    config = RunConfig(
        run_type=RunType.MANUAL,
        target_date=parsed_date,
        providers=provider_list,
        tags=tag_list,
        skip_features=skip_features,
    )
    
    console.print(f"\n[bold blue]ATLAS Pipeline Run[/bold blue]")
    console.print(f"Target Date: {config.target_date}")
    console.print(f"Providers: {provider_list or 'all configured'}")
    console.print(f"Tags Filter: {tag_list or 'none'}\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running pipeline...", total=None)
        
        orchestrator = PipelineOrchestrator()
        result = asyncio.run(orchestrator.run(config))
        
        progress.remove_task(task)
    
    # Display results
    table = Table(title="Pipeline Run Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Run ID", str(result.run_id))
    table.add_row("Status", result.status.value)
    table.add_row("Duration", f"{result.duration_seconds:.2f}s")
    table.add_row("Records Inserted", str(result.records_inserted))
    table.add_row("Records Updated", str(result.records_updated))
    
    console.print(table)
    
    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in result.errors:
            console.print(f"  • {error}")


@app.command()
def backfill(
    start_date: str = typer.Option(
        ..., "--start", "-s",
        help="Start date (YYYY-MM-DD).",
    ),
    end_date: str = typer.Option(
        ..., "--end", "-e",
        help="End date (YYYY-MM-DD).",
    ),
    providers: Optional[str] = typer.Option(
        None, "--providers", "-p",
        help="Comma-separated list of providers to run.",
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", "-t",
        help="Comma-separated list of instrument tags to filter.",
    ),
    batch_size: int = typer.Option(
        30, "--batch-size", "-b",
        help="Number of days per batch.",
    ),
    skip_features: bool = typer.Option(
        False, "--skip-features",
        help="Skip feature calculation.",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show what would be done without executing.",
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Enable verbose logging.",
    ),
) -> None:
    """Run a backfill for a date range."""
    setup_logging(level="DEBUG" if verbose else "INFO", format_type="text")
    
    from atlas.pipeline.backfill import BackfillManager, BackfillConfig
    
    parsed_start = parse_date(start_date)
    parsed_end = parse_date(end_date)
    provider_list = providers.split(",") if providers else None
    tag_list = tags.split(",") if tags else None
    
    config = BackfillConfig(
        start_date=parsed_start,
        end_date=parsed_end,
        providers=provider_list,
        tags=tag_list,
        batch_size_days=batch_size,
        skip_features=skip_features,
    )
    
    manager = BackfillManager()
    
    # Show estimate
    estimate = asyncio.run(manager.estimate_duration(config))
    
    console.print(f"\n[bold blue]ATLAS Backfill[/bold blue]")
    console.print(f"Date Range: {parsed_start} to {parsed_end}")
    console.print(f"Total Dates: {estimate['total_dates']}")
    console.print(f"Batches: {estimate['batches']}")
    console.print(f"Estimated Time: {estimate['estimated_minutes']:.1f} minutes\n")
    
    if dry_run:
        console.print("[yellow]Dry run - no data will be fetched.[/yellow]")
        return
    
    if not typer.confirm("Proceed with backfill?"):
        raise typer.Abort()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Running backfill...", total=None)
        
        result = asyncio.run(manager.run(config))
        
        progress.remove_task(task)
    
    # Display results
    table = Table(title="Backfill Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Dates", str(result.total_dates_processed))
    table.add_row("Successful", str(result.successful_dates))
    table.add_row("Failed", str(result.failed_dates))
    table.add_row("Success Rate", f"{result.success_rate:.1f}%")
    table.add_row("Duration", f"{result.duration_seconds:.1f}s")
    table.add_row("Records Inserted", str(result.total_records_inserted))
    table.add_row("Records Updated", str(result.total_records_updated))
    
    console.print(table)
    
    if result.errors:
        console.print("\n[bold red]Errors by Date:[/bold red]")
        for run_date, errors in list(result.errors.items())[:5]:
            console.print(f"  {run_date}:")
            for error in errors:
                console.print(f"    • {error}")
        if len(result.errors) > 5:
            console.print(f"  ... and {len(result.errors) - 5} more dates with errors")


@app.command()
def status() -> None:
    """Show pipeline status and recent runs."""
    setup_logging(level="WARNING", format_type="text")
    
    from atlas.storage.database import get_database
    from atlas.storage.repository import PipelineRunRepository
    
    db = get_database()
    
    console.print(f"\n[bold blue]ATLAS Status[/bold blue]")
    
    # Database health
    if db.health_check():
        console.print("Database: [green]Connected[/green]")
    else:
        console.print("Database: [red]Disconnected[/red]")
        return
    
    # Recent runs
    with db.session() as session:
        repo = PipelineRunRepository(session)
        latest = repo.get_latest_run()
        
        if latest:
            console.print(f"\nLatest Run:")
            console.print(f"  ID: {latest.run_id}")
            console.print(f"  Type: {latest.run_type}")
            console.print(f"  Date: {latest.run_date}")
            console.print(f"  Status: {latest.status}")
            console.print(f"  Started: {latest.start_time}")
        else:
            console.print("\nNo runs found.")


@app.command()
def init_db(
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Drop and recreate tables.",
    ),
) -> None:
    """Initialize the database schema."""
    setup_logging(level="INFO", format_type="text")
    
    from atlas.storage.database import get_database
    
    db = get_database()
    
    if force:
        if not typer.confirm("This will DROP all existing tables. Continue?"):
            raise typer.Abort()
        console.print("Dropping existing tables...")
        db.drop_tables()
    
    console.print("Creating tables...")
    db.create_tables()
    console.print("[green]Database initialized successfully.[/green]")


@app.command()
def instruments(
    action: str = typer.Argument(
        ..., help="Action: list, add-tag, remove-tag, sync"
    ),
    ticker: Optional[str] = typer.Option(
        None, "--ticker", "-t",
        help="Ticker symbol.",
    ),
    tag: Optional[str] = typer.Option(
        None, "--tag",
        help="Tag name.",
    ),
) -> None:
    """Manage instruments and tags."""
    setup_logging(level="WARNING", format_type="text")
    
    from atlas.storage.database import get_database
    from atlas.storage.repository import InstrumentRepository
    
    db = get_database()
    
    with db.session() as session:
        repo = InstrumentRepository(session)
        
        if action == "list":
            instruments = repo.get_active()
            
            table = Table(title=f"Instruments ({len(instruments)} active)")
            table.add_column("ID", style="dim")
            table.add_column("Ticker", style="cyan")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Tags")
            
            for inst in instruments[:50]:  # Limit display
                tags = repo.get_tags(inst.instrument_id)
                table.add_row(
                    str(inst.instrument_id),
                    inst.ticker,
                    inst.name or "",
                    inst.asset_type,
                    ", ".join(tags),
                )
            
            console.print(table)
            
            if len(instruments) > 50:
                console.print(f"... showing 50 of {len(instruments)}")
        
        elif action == "add-tag":
            if not ticker or not tag:
                console.print("[red]--ticker and --tag required[/red]")
                return
            
            inst = repo.get_by_ticker(ticker)
            if not inst:
                console.print(f"[red]Instrument not found: {ticker}[/red]")
                return
            
            repo.add_tag(inst.instrument_id, tag)
            console.print(f"[green]Added tag '{tag}' to {ticker}[/green]")
        
        elif action == "remove-tag":
            if not ticker or not tag:
                console.print("[red]--ticker and --tag required[/red]")
                return
            
            inst = repo.get_by_ticker(ticker)
            if not inst:
                console.print(f"[red]Instrument not found: {ticker}[/red]")
                return
            
            repo.remove_tag(inst.instrument_id, tag)
            console.print(f"[green]Removed tag '{tag}' from {ticker}[/green]")
        
        else:
            console.print(f"[red]Unknown action: {action}[/red]")


@app.command()
def dashboard() -> None:
    """Launch the Streamlit dashboard."""
    import subprocess
    import sys
    
    console.print("[bold blue]Launching ATLAS Dashboard...[/bold blue]")
    
    dashboard_path = "src/atlas/dashboard/app.py"
    
    subprocess.run([
        sys.executable, "-m", "streamlit", "run", dashboard_path,
        "--server.headless", "true",
    ])


@app.command()
def version() -> None:
    """Show version information."""
    from atlas import __version__
    
    console.print(f"ATLAS v{__version__}")


if __name__ == "__main__":
    app()
