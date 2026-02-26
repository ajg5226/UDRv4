"""Data providers for external data sources."""

from atlas.providers.base import BaseProvider, ProviderResult, InstrumentInfo
from atlas.providers.registry import ProviderRegistry, get_provider_registry
from atlas.providers.tiingo import TiingoProvider
from atlas.providers.fred import FredProvider

__all__ = [
    "BaseProvider",
    "ProviderResult",
    "InstrumentInfo",
    "ProviderRegistry",
    "get_provider_registry",
    "TiingoProvider",
    "FredProvider",
]
