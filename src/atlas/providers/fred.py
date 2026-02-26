"""FRED data provider for macroeconomic data."""

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

import httpx
import pandas as pd
import yaml
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from atlas.core.config import get_settings, PROJECT_ROOT
from atlas.core.exceptions import ProviderError, RateLimitError
from atlas.core.logging import get_logger
from atlas.providers.base import (
    BaseProvider,
    InstrumentInfo,
    ProviderResult,
    ProviderType,
    ValidationResult,
    ValidationStatus,
)

logger = get_logger(__name__)


class FredProvider(BaseProvider):
    """
    FRED (Federal Reserve Economic Data) provider.
    
    Provides access to macroeconomic indicators organized by category:
    - Growth (GDP, employment, production)
    - Liquidity (money supply, rates, spreads)
    - Risk Appetite (VIX, credit spreads, inflation)
    """
    
    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initialize FRED provider.
        
        Args:
            api_key: FRED API key. If not provided, will try to load from
                    environment or Key Vault.
        """
        self._api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        self._settings = get_settings().providers.fred
        self._series_config: Optional[dict] = None
    
    @property
    def name(self) -> str:
        return "fred"
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.MACRO
    
    @property
    def is_enabled(self) -> bool:
        return self._settings.enabled
    
    @property
    def api_key(self) -> str:
        """Get API key, loading from environment if needed."""
        if self._api_key is None:
            # Try environment variable first
            self._api_key = os.getenv("FRED_API_KEY")
            
            if self._api_key is None:
                # Try Key Vault (placeholder for now)
                try:
                    from atlas.core.secrets import get_secret
                    self._api_key = get_secret(self._settings.api_key_secret)
                except Exception:
                    pass
            
            if self._api_key is None:
                raise ProviderError(
                    "FRED API key not configured",
                    provider_name=self.name,
                    retryable=False,
                )
        
        return self._api_key
    
    @property
    def series_config(self) -> dict:
        """Get series configuration, loading from YAML if needed."""
        if self._series_config is None:
            config_path = PROJECT_ROOT / self._settings.series_config
            if config_path.exists():
                with open(config_path) as f:
                    self._series_config = yaml.safe_load(f)
            else:
                logger.warning(f"FRED series config not found: {config_path}")
                self._series_config = {}
        return self._series_config
    
    async def initialize(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url,
            timeout=self._settings.timeout_seconds,
        )
        logger.info("FRED provider initialized")
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not initialized."""
        if self._client is None:
            raise ProviderError(
                "FRED provider not initialized. Call initialize() first.",
                provider_name=self.name,
                retryable=False,
            )
        return self._client
    
    def get_all_series(self) -> list[dict[str, Any]]:
        """
        Get all configured series with their metadata.
        
        Returns:
            List of series info dicts with category, subcategory, id, name, frequency
        """
        series = []
        
        for category, subcategories in self.series_config.items():
            if not isinstance(subcategories, dict):
                continue
                
            for subcategory, series_list in subcategories.items():
                if not isinstance(series_list, list):
                    continue
                    
                for item in series_list:
                    series.append({
                        "fred_id": item["id"],
                        "name": item["name"],
                        "category": category,
                        "subcategory": subcategory,
                        "frequency": item.get("frequency", "daily"),
                    })
        
        return series
    
    def get_series_by_category(self, category: str) -> list[dict[str, Any]]:
        """Get series for a specific category."""
        return [s for s in self.get_all_series() if s["category"] == category]
    
    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> Any:
        """Make an API request with retry logic."""
        params["api_key"] = self.api_key
        params["file_type"] = "json"
        
        response = await self.client.get(endpoint, params=params)
        
        if response.status_code == 429:
            raise RateLimitError(
                "FRED rate limit exceeded",
                provider_name=self.name,
                retry_after=60,
            )
        
        if response.status_code == 400:
            error_data = response.json()
            raise ProviderError(
                f"FRED API error: {error_data.get('error_message', 'Unknown error')}",
                provider_name=self.name,
                details=error_data,
            )
        
        if response.status_code != 200:
            raise ProviderError(
                f"FRED API error: {response.status_code}",
                provider_name=self.name,
                details={"response": response.text},
            )
        
        return response.json()
    
    async def fetch_data(
        self,
        target_date: date,
        instruments: Optional[list[str]] = None,
    ) -> ProviderResult:
        """
        Fetch macro data for a specific date.
        
        Args:
            target_date: The date to fetch data for
            instruments: Optional list of FRED series IDs. If None, fetch all configured.
            
        Returns:
            ProviderResult with macro data
        """
        start_time = datetime.utcnow()
        
        if instruments is None:
            # Fetch all configured series
            series_info = self.get_all_series()
            instruments = [s["fred_id"] for s in series_info]
        
        logger.info(
            f"Fetching FRED data",
            date=str(target_date),
            series_count=len(instruments),
        )
        
        all_data = []
        failed_instruments = []
        
        for series_id in instruments:
            try:
                data = await self._fetch_series_data(
                    series_id,
                    target_date,
                    target_date,
                )
                if data:
                    all_data.extend(data)
            except ProviderError as e:
                logger.warning(f"Failed to fetch {series_id}", error=str(e))
                failed_instruments.append(series_id)
            except Exception as e:
                logger.warning(f"Unexpected error fetching {series_id}", error=str(e))
                failed_instruments.append(series_id)
        
        # Convert to DataFrame
        df = pd.DataFrame(all_data) if all_data else pd.DataFrame()
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        
        result = ProviderResult(
            provider_name=self.name,
            fetch_date=target_date,
            data=df,
            records_fetched=len(df),
            fetch_duration_seconds=duration,
            success=len(failed_instruments) == 0,
            partial_failure=len(failed_instruments) > 0 and len(all_data) > 0,
            failed_instruments=failed_instruments,
        )
        
        # Validate
        result.validation = self.validate(df)
        
        logger.info(
            f"FRED fetch complete",
            records=len(df),
            failed=len(failed_instruments),
            duration_seconds=duration,
        )
        
        return result
    
    async def _fetch_series_data(
        self,
        series_id: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch data for a single series."""
        params = {
            "series_id": series_id,
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
            "sort_order": "asc",
        }
        
        data = await self._make_request("/series/observations", params)
        
        observations = data.get("observations", [])
        
        records = []
        for obs in observations:
            # FRED returns "." for missing values
            value = obs.get("value")
            if value == "." or value is None:
                value = None
            else:
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = None
            
            records.append({
                "fred_id": series_id,
                "obs_date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                "value": value,
            })
        
        return records
    
    async def fetch_date_range(
        self,
        series_id: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Fetch data for a single series over a date range.
        
        Useful for backfills.
        """
        data = await self._fetch_series_data(series_id, start_date, end_date)
        return pd.DataFrame(data)
    
    async def fetch_series_info(self, series_id: str) -> dict[str, Any]:
        """Fetch metadata about a series."""
        data = await self._make_request(
            "/series",
            {"series_id": series_id},
        )
        
        if data.get("seriess"):
            series = data["seriess"][0]
            return {
                "fred_id": series["id"],
                "name": series.get("title"),
                "frequency": series.get("frequency_short"),
                "units": series.get("units"),
                "seasonal_adj": series.get("seasonal_adjustment_short"),
                "notes": series.get("notes"),
            }
        
        return {}
    
    async def fetch_instruments(self) -> list[InstrumentInfo]:
        """
        Get configured macro series as 'instruments'.
        
        Note: FRED doesn't have a traditional instrument concept,
        but we treat each series as an instrument for consistency.
        """
        series = self.get_all_series()
        
        instruments = []
        for s in series:
            instruments.append(InstrumentInfo(
                ticker=s["fred_id"],
                name=s["name"],
                asset_type="macro",
                provider_id=s["fred_id"],
            ))
        
        return instruments
    
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate fetched macro data."""
        if data.empty:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                message="No data returned",
            )
        
        # Check required columns
        required = ["fred_id", "obs_date", "value"]
        missing = [col for col in required if col not in data.columns]
        if missing:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                message=f"Missing required columns: {missing}",
                details={"missing_columns": missing},
            )
        
        # Check for null values (common in FRED for certain dates)
        null_count = data["value"].isnull().sum()
        null_pct = null_count / len(data) * 100 if len(data) > 0 else 0
        
        if null_pct > 50:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                message=f"High null rate in values: {null_pct:.1f}%",
                details={"null_count": null_count, "null_pct": null_pct},
            )
        
        return ValidationResult(
            status=ValidationStatus.VALID,
            message="Data validation passed",
            details={
                "record_count": len(data),
                "null_count": null_count,
                "series_count": data["fred_id"].nunique(),
            },
        )
    
    def get_expected_columns(self) -> list[str]:
        """Get expected columns for FRED data."""
        return ["fred_id", "obs_date", "value"]
