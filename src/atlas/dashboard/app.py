"""Main Streamlit dashboard application for ATLAS."""

import os
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

# Page config must be first Streamlit command
st.set_page_config(
    page_title="ATLAS Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from atlas.dashboard.auth import check_authentication, show_login
from atlas.core.config import get_settings, is_development_environment
from atlas.core.exceptions import ConfigurationError
from atlas.core.logging import setup_logging
from atlas.storage.database import get_database
from atlas.storage.repository import (
    InstrumentRepository,
    MacroRepository,
    MacroSeriesRepository,
    OHLCVRepository,
    PipelineRunRepository,
)

# Setup logging
setup_logging(level="WARNING", format_type="text")


def main() -> None:
    """Main dashboard entry point."""
    settings = get_settings()

    # Authentication
    if not settings.dashboard.auth.enabled:
        if not is_development_environment(settings.environment):
            raise ConfigurationError(
                "Dashboard authentication cannot be disabled outside development environments",
                details={"environment": settings.environment},
            )
    else:
        if not check_authentication():
            show_login()
            return
    
    # Sidebar navigation
    st.sidebar.title("📊 ATLAS Dashboard")
    
    page = st.sidebar.radio(
        "Navigation",
        ["Overview", "Price Data", "Macro Data", "Features", "Pipeline Runs"],
        label_visibility="collapsed",
    )
    
    # User info
    if "username" in st.session_state:
        st.sidebar.markdown("---")
        st.sidebar.write(f"Logged in as: **{st.session_state.username}**")
        if st.sidebar.button("Logout"):
            del st.session_state["authenticated"]
            del st.session_state["username"]
            st.rerun()
    
    # Route to page
    if page == "Overview":
        show_overview_page()
    elif page == "Price Data":
        show_price_data_page()
    elif page == "Macro Data":
        show_macro_data_page()
    elif page == "Features":
        show_features_page()
    elif page == "Pipeline Runs":
        show_pipeline_runs_page()


def show_overview_page() -> None:
    """Show the overview/home page."""
    st.title("ATLAS Overview")
    
    db = get_database()
    
    # Check database connectivity
    if not db.health_check():
        st.error("Database connection failed!")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with db.session() as session:
        # Instrument count
        inst_repo = InstrumentRepository(session)
        instruments = inst_repo.get_active()
        col1.metric("Active Instruments", len(instruments))
        
        # Macro series count
        macro_repo = MacroSeriesRepository(session)
        series = macro_repo.get_active()
        col2.metric("Macro Series", len(series))
        
        # Latest run
        run_repo = PipelineRunRepository(session)
        latest_run = run_repo.get_latest_run()
        if latest_run:
            col3.metric("Latest Run Status", latest_run.status)
            col4.metric("Latest Run Date", str(latest_run.run_date))
        else:
            col3.metric("Latest Run Status", "No runs")
            col4.metric("Latest Run Date", "-")
    
    st.markdown("---")
    
    # Recent runs table
    st.subheader("Recent Pipeline Runs")
    
    with db.session() as session:
        run_repo = PipelineRunRepository(session)
        # Get recent runs (simple query)
        from sqlalchemy import select
        from atlas.storage.models import PipelineRun
        
        stmt = select(PipelineRun).order_by(PipelineRun.start_time.desc()).limit(10)
        runs = list(session.scalars(stmt))
        
        if runs:
            runs_data = []
            for run in runs:
                runs_data.append({
                    "Run ID": run.run_id,
                    "Type": run.run_type,
                    "Date": run.run_date,
                    "Status": run.status,
                    "Started": run.start_time,
                    "Records": (run.records_inserted or 0) + (run.records_updated or 0),
                })
            
            st.dataframe(pd.DataFrame(runs_data), use_container_width=True)
        else:
            st.info("No pipeline runs found.")


def show_price_data_page() -> None:
    """Show price data exploration page."""
    st.title("Price Data")
    
    db = get_database()
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with db.session() as session:
        inst_repo = InstrumentRepository(session)
        instruments = inst_repo.get_active()
        ticker_options = [i.ticker for i in instruments]
    
    with col1:
        selected_tickers = st.multiselect(
            "Select Instruments",
            options=ticker_options[:100],  # Limit options
            default=ticker_options[:3] if ticker_options else [],
            max_selections=10,
        )
    
    with col2:
        start_date = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=30),
        )
    
    with col3:
        end_date = st.date_input(
            "End Date",
            value=date.today(),
        )
    
    if not selected_tickers:
        st.info("Select at least one instrument to view data.")
        return
    
    # Fetch data
    with db.session() as session:
        inst_repo = InstrumentRepository(session)
        ohlcv_repo = OHLCVRepository(session)
        
        # Get instrument IDs
        selected_instruments = inst_repo.get_by_tickers(selected_tickers)
        instrument_ids = [i.instrument_id for i in selected_instruments]
        
        # Get price data
        df = ohlcv_repo.get_as_dataframe(
            instrument_ids=instrument_ids,
            start_date=start_date,
            end_date=end_date,
        )
    
    if df.empty:
        st.warning("No data found for the selected criteria.")
        return
    
    # Add ticker column
    ticker_map = {i.instrument_id: i.ticker for i in selected_instruments}
    df["ticker"] = df["instrument_id"].map(ticker_map)
    
    # Display chart
    st.subheader("Price Chart (Adjusted Close)")
    
    chart_data = df.pivot(
        index="trade_date",
        columns="ticker",
        values="adj_close",
    )
    st.line_chart(chart_data)
    
    # Display table
    st.subheader("Data Table")
    
    display_cols = ["ticker", "trade_date", "open", "high", "low", "close", "volume", "adj_close"]
    display_df = df[display_cols].sort_values(["ticker", "trade_date"], ascending=[True, False])
    
    st.dataframe(display_df, use_container_width=True)
    
    # Download button
    csv = display_df.to_csv(index=False)
    st.download_button(
        "Download CSV",
        csv,
        "atlas_price_data.csv",
        "text/csv",
    )


def show_macro_data_page() -> None:
    """Show macro data exploration page."""
    st.title("Macro Data")
    
    db = get_database()
    
    # Category filter
    col1, col2, col3 = st.columns(3)
    
    with col1:
        category = st.selectbox(
            "Category",
            ["growth", "liquidity", "risk_appetite", "All"],
        )
    
    with col2:
        start_date = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=365),
            key="macro_start",
        )
    
    with col3:
        end_date = st.date_input(
            "End Date",
            value=date.today(),
            key="macro_end",
        )
    
    # Fetch series list
    with db.session() as session:
        series_repo = MacroSeriesRepository(session)
        
        if category == "All":
            series_list = series_repo.get_active()
        else:
            series_list = series_repo.get_by_category(category)
    
    if not series_list:
        st.info("No macro series found.")
        return
    
    # Series selector
    series_options = {s.fred_id: f"{s.fred_id} - {s.name}" for s in series_list}
    selected_series = st.multiselect(
        "Select Series",
        options=list(series_options.keys()),
        format_func=lambda x: series_options[x],
        default=list(series_options.keys())[:5],
        max_selections=10,
    )
    
    if not selected_series:
        st.info("Select at least one series to view data.")
        return
    
    # Fetch data
    with db.session() as session:
        series_repo = MacroSeriesRepository(session)
        macro_repo = MacroRepository(session)
        
        # Get series IDs
        series_ids = [s.series_id for s in series_list if s.fred_id in selected_series]
        
        # Get macro data
        df = macro_repo.get_as_dataframe(
            series_ids=series_ids,
            start_date=start_date,
            end_date=end_date,
        )
    
    if df.empty:
        st.warning("No data found for the selected criteria.")
        return
    
    # Add series name
    series_map = {s.series_id: s.fred_id for s in series_list}
    df["fred_id"] = df["series_id"].map(series_map)
    
    # Display chart
    st.subheader("Macro Series Chart")
    
    chart_data = df.pivot(
        index="obs_date",
        columns="fred_id",
        values="value",
    )
    st.line_chart(chart_data)
    
    # Display table
    st.subheader("Data Table")
    st.dataframe(df[["fred_id", "obs_date", "value"]], use_container_width=True)


def show_features_page() -> None:
    """Show features exploration page."""
    st.title("Features")
    
    st.info("Feature exploration coming soon. Features are calculated as part of the pipeline.")
    
    # Placeholder for feature exploration
    st.markdown("""
    ### Available Features
    
    **Returns**
    - daily_return
    - log_return
    - cumulative_return_5d, 21d, 63d, 126d, 252d
    
    **Volatility**
    - realized_vol_21d
    - realized_vol_63d
    
    **Momentum**
    - sma_20, sma_50, sma_200
    - rsi_14
    """)


def show_pipeline_runs_page() -> None:
    """Show pipeline runs history page."""
    st.title("Pipeline Runs")
    
    db = get_database()
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        run_type_filter = st.selectbox(
            "Run Type",
            ["All", "nightly", "backfill", "manual"],
        )
    
    with col2:
        status_filter = st.selectbox(
            "Status",
            ["All", "success", "partial", "failed", "running"],
        )
    
    # Fetch runs
    with db.session() as session:
        from sqlalchemy import select
        from atlas.storage.models import PipelineRun
        
        stmt = select(PipelineRun).order_by(PipelineRun.start_time.desc()).limit(100)
        
        if run_type_filter != "All":
            stmt = stmt.where(PipelineRun.run_type == run_type_filter)
        
        if status_filter != "All":
            stmt = stmt.where(PipelineRun.status == status_filter)
        
        runs = list(session.scalars(stmt))
    
    if not runs:
        st.info("No pipeline runs found matching criteria.")
        return
    
    # Display table
    runs_data = []
    for run in runs:
        duration = None
        if run.end_time and run.start_time:
            duration = (run.end_time - run.start_time).total_seconds()
        
        runs_data.append({
            "Run ID": run.run_id,
            "Type": run.run_type,
            "Date": run.run_date,
            "Status": run.status,
            "Started": run.start_time,
            "Duration (s)": f"{duration:.1f}" if duration else "-",
            "Inserted": run.records_inserted or 0,
            "Updated": run.records_updated or 0,
        })
    
    df = pd.DataFrame(runs_data)
    
    # Color status
    st.dataframe(
        df,
        use_container_width=True,
        column_config={
            "Status": st.column_config.TextColumn(
                "Status",
                help="Pipeline run status",
            ),
        },
    )
    
    # Run details
    st.subheader("Run Details")
    
    selected_run_id = st.selectbox(
        "Select Run ID",
        options=[r.run_id for r in runs],
    )
    
    if selected_run_id:
        selected_run = next((r for r in runs if r.run_id == selected_run_id), None)
        if selected_run:
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("**Run Information**")
                st.json({
                    "run_id": selected_run.run_id,
                    "run_type": selected_run.run_type,
                    "run_date": str(selected_run.run_date),
                    "status": selected_run.status,
                    "start_time": str(selected_run.start_time),
                    "end_time": str(selected_run.end_time) if selected_run.end_time else None,
                    "providers_run": selected_run.providers_run,
                    "tags_filter": selected_run.tags_filter,
                })
            
            with col2:
                st.write("**Results**")
                st.metric("Records Inserted", selected_run.records_inserted or 0)
                st.metric("Records Updated", selected_run.records_updated or 0)
                
                if selected_run.errors:
                    st.error("Errors:")
                    st.text(selected_run.errors)


if __name__ == "__main__":
    main()
