"""Base provider interface and data structures."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

import pandas as pd


class ProviderType(str, Enum):
    """Types of data providers."""
    
    MARKET_DATA = "market_data"
    MACRO = "macro"
    ALTERNATIVE = "alternative"
    FUNDAMENTAL = "fundamental"


class ValidationStatus(str, Enum):
    """Validation result status."""
    
    VALID = "valid"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class InstrumentInfo:
    """Information about an available instrument from a provider."""
    
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    asset_type: str = "equity"
    currency: str = "USD"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    
    # Provider-specific identifiers
    provider_id: Optional[str] = None
    
    # Additional metadata
    sector: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "exchange": self.exchange,
            "asset_type": self.asset_type,
            "currency": self.currency,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "provider_id": self.provider_id,
            "sector": self.sector,
            "industry": self.industry,
            "country": self.country,
        }


@dataclass
class ValidationResult:
    """Result of data validation."""
    
    status: ValidationStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed (valid or warning)."""
        return self.status in (ValidationStatus.VALID, ValidationStatus.WARNING)


@dataclass
class ProviderResult:
    """Result from a provider fetch operation."""
    
    provider_name: str
    fetch_date: date
    data: pd.DataFrame
    
    # Metadata
    records_fetched: int = 0
    fetch_duration_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Validation
    validation: Optional[ValidationResult] = None
    
    # Error handling
    success: bool = True
    error_message: Optional[str] = None
    partial_failure: bool = False
    failed_instruments: list[str] = field(default_factory=list)
    
    # Raw data for archiving
    raw_response: Optional[Any] = None
    
    def __post_init__(self) -> None:
        if self.records_fetched == 0 and not self.data.empty:
            self.records_fetched = len(self.data)


class BaseProvider(ABC):
    """
    Abstract base class for all data providers.
    
    All providers must implement:
    - name: Unique provider identifier
    - provider_type: Category of data (market_data, macro, etc.)
    - fetch_data(): Fetch data for a specific date
    - fetch_instruments(): Get available instruments
    - validate(): Validate fetched data
    
    Providers should also implement:
    - _initialize(): Called once during setup
    - _authenticate(): Handle API authentication
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g., 'tiingo', 'fred')."""
        pass
    
    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Provider category."""
        pass
    
    @property
    def is_enabled(self) -> bool:
        """Whether this provider is enabled."""
        return True
    
    @abstractmethod
    async def fetch_data(
        self,
        target_date: date,
        instruments: Optional[list[str]] = None,
    ) -> ProviderResult:
        """
        Fetch data for a specific date.
        
        Args:
            target_date: The date to fetch data for
            instruments: Optional list of tickers. If None, fetch all available.
            
        Returns:
            ProviderResult containing the fetched data and metadata
        """
        pass
    
    @abstractmethod
    async def fetch_instruments(self) -> list[InstrumentInfo]:
        """
        Fetch available instruments from this provider.
        
        Returns:
            List of InstrumentInfo for each available instrument
        """
        pass
    
    @abstractmethod
    def validate(self, data: pd.DataFrame) -> ValidationResult:
        """
        Validate fetched data against expected schema and quality rules.
        
        Args:
            data: DataFrame to validate
            
        Returns:
            ValidationResult indicating validity
        """
        pass
    
    async def initialize(self) -> None:
        """Initialize the provider (called once during setup)."""
        pass
    
    async def close(self) -> None:
        """Clean up resources."""
        pass
    
    def get_expected_columns(self) -> list[str]:
        """
        Get expected column names for this provider's data.
        
        Override in subclasses.
        """
        return []
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', type='{self.provider_type.value}')>"
