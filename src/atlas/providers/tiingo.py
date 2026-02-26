"""Tiingo data provider for market data."""

import os
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx
import pandas as pd
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from atlas.core.config import get_settings
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


class TiingoProvider(BaseProvider):
    """
    Tiingo data provider for daily OHLCV data.
    
    Supports:
    - US equities
    - ETFs
    - Mutual funds
    - Adjusted and unadjusted prices
    """
    
    def __init__(self, api_key: Optional[str] = None) -> None:
        """
        Initialize Tiingo provider.
        
        Args:
            api_key: Tiingo API key. If not provided, will try to load from
                    environment or Key Vault.
        """
        self._api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        self._settings = get_settings().providers.tiingo
    
    @property
    def name(self) -> str:
        return "tiingo"
    
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.MARKET_DATA
    
    @property
    def is_enabled(self) -> bool:
        return self._settings.enabled
    
    @property
    def api_key(self) -> str:
        """Get API key, loading from environment if needed."""
        if self._api_key is None:
            # Try environment variable first
            self._api_key = os.getenv("TIINGO_API_KEY")
            
            if self._api_key is None:
                # Try Key Vault (placeholder for now)
                try:
                    from atlas.core.secrets import get_secret
                    self._api_key = get_secret(self._settings.api_key_secret)
                except Exception:
                    pass
            
            if self._api_key is None:
                raise ProviderError(
                    "Tiingo API key not configured",
                    provider_name=self.name,
                    retryable=False,
                )
        
        return self._api_key
    
    async def initialize(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Token {self.api_key}",
            },
            timeout=self._settings.timeout_seconds,
        )
        logger.info("Tiingo provider initialized")
    
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
                "Tiingo provider not initialized. Call initialize() first.",
                provider_name=self.name,
                retryable=False,
            )
        return self._client
    
    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Make an API request with retry logic."""
        response = await self.client.get(endpoint, params=params)
        
        if response.status_code == 429:
            raise RateLimitError(
                "Tiingo rate limit exceeded",
                provider_name=self.name,
                retry_after=60,
            )
        
        if response.status_code == 401:
            raise ProviderError(
                "Tiingo authentication failed",
                provider_name=self.name,
                retryable=False,
            )
        
        if response.status_code != 200:
            raise ProviderError(
                f"Tiingo API error: {response.status_code}",
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
        Fetch OHLCV data for a specific date.
        
        Args:
            target_date: The date to fetch data for
            instruments: Optional list of tickers. If None, fetch all.
            
        Returns:
            ProviderResult with OHLCV data
        """
        start_time = datetime.utcnow()
        
        if instruments is None:
            # Fetch all available instruments
            instrument_infos = await self.fetch_instruments()
            instruments = [i.ticker for i in instrument_infos]
        
        logger.info(
            f"Fetching Tiingo data",
            date=str(target_date),
            instrument_count=len(instruments),
        )
        
        all_data = []
        failed_instruments = []
        
        # Fetch data for each instrument
        # Note: Tiingo's EOD API is per-ticker, so we need to batch
        for ticker in instruments:
            try:
                data = await self._fetch_ticker_data(ticker, target_date, target_date)
                if data:
                    all_data.extend(data)
            except ProviderError as e:
                logger.warning(f"Failed to fetch {ticker}", error=str(e))
                failed_instruments.append(ticker)
            except Exception as e:
                logger.warning(f"Unexpected error fetching {ticker}", error=str(e))
                failed_instruments.append(ticker)
        
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
            f"Tiingo fetch complete",
            records=len(df),
            failed=len(failed_instruments),
            duration_seconds=duration,
        )
        
        return result
    
    async def _fetch_ticker_data(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        """Fetch data for a single ticker."""
        params = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "resampleFreq": "daily",
        }
        
        endpoint = f"/tiingo/daily/{ticker}/prices"
        data = await self._make_request(endpoint, params)
        
        # Transform to our format
        records = []
        for row in data:
            records.append({
                "ticker": ticker,
                "trade_date": datetime.fromisoformat(row["date"].replace("Z", "+00:00")).date(),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "adj_open": row.get("adjOpen"),
                "adj_high": row.get("adjHigh"),
                "adj_low": row.get("adjLow"),
                "adj_close": row.get("adjClose"),
                "adj_volume": row.get("adjVolume"),
                "dividend": row.get("divCash"),
                "split_factor": row.get("splitFactor"),
            })
        
        return records
    
    async def fetch_date_range(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Fetch data for a single ticker over a date range.
        
        Useful for backfills.
        """
        data = await self._fetch_ticker_data(ticker, start_date, end_date)
        return pd.DataFrame(data)
    
    async def fetch_instruments(self) -> list[InstrumentInfo]:
        """Fetch all available instruments from Tiingo."""
        logger.info("Fetching Tiingo instrument universe")
        
        # Tiingo provides a CSV endpoint for supported tickers
        response = await self.client.get(
            "/tiingo/daily",
            headers={"Accept": "application/json"},
        )
        
        if response.status_code != 200:
            raise ProviderError(
                f"Failed to fetch Tiingo instruments: {response.status_code}",
                provider_name=self.name,
            )
        
        data = response.json()
        
        instruments = []
        for item in data:
            try:
                start = datetime.fromisoformat(item["startDate"].replace("Z", "+00:00")).date() if item.get("startDate") else None
                end = datetime.fromisoformat(item["endDate"].replace("Z", "+00:00")).date() if item.get("endDate") else None
            except (ValueError, TypeError):
                start = None
                end = None
            
            instruments.append(InstrumentInfo(
                ticker=item["ticker"],
                name=item.get("name"),
                exchange=item.get("exchange"),
                asset_type=item.get("assetType", "equity").lower(),
                currency=item.get("priceCurrency", "USD"),
                start_date=start,
                end_date=end,
                provider_id=item["ticker"],
            ))
        
        logger.info(f"Fetched {len(instruments)} instruments from Tiingo")
        return instruments
    
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """Validate fetched OHLCV data."""
        if data.empty:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                message="No data returned",
            )
        
        # Check required columns
        required = ["ticker", "trade_date", "open", "high", "low", "close"]
        missing = [col for col in required if col not in data.columns]
        if missing:
            return ValidationResult(
                status=ValidationStatus.ERROR,
                message=f"Missing required columns: {missing}",
                details={"missing_columns": missing},
            )
        
        # Check for nulls in critical fields
        null_counts = data[["open", "high", "low", "close"]].isnull().sum()
        total_nulls = null_counts.sum()
        
        if total_nulls > 0:
            null_pct = total_nulls / (len(data) * 4) * 100
            if null_pct > 10:
                return ValidationResult(
                    status=ValidationStatus.WARNING,
                    message=f"High null rate in price data: {null_pct:.1f}%",
                    details={"null_counts": null_counts.to_dict()},
                )
        
        # Check price sanity (no negative prices, high > low, etc.)
        price_issues = []
        
        if (data["high"] < data["low"]).any():
            price_issues.append("high < low detected")
        
        if (data[["open", "high", "low", "close"]] < 0).any().any():
            price_issues.append("negative prices detected")
        
        if price_issues:
            return ValidationResult(
                status=ValidationStatus.WARNING,
                message=f"Price data issues: {', '.join(price_issues)}",
                details={"issues": price_issues},
            )
        
        return ValidationResult(
            status=ValidationStatus.VALID,
            message="Data validation passed",
            details={"record_count": len(data)},
        )
    
    def get_expected_columns(self) -> list[str]:
        """Get expected columns for Tiingo data."""
        return [
            "ticker",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "adj_open",
            "adj_high",
            "adj_low",
            "adj_close",
            "adj_volume",
            "dividend",
            "split_factor",
        ]
