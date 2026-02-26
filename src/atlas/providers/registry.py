"""Provider registry for managing data providers."""

from functools import lru_cache
from typing import Optional, Type

from atlas.core.config import get_settings
from atlas.core.exceptions import ConfigurationError
from atlas.core.logging import get_logger
from atlas.providers.base import BaseProvider, ProviderType

logger = get_logger(__name__)


class ProviderRegistry:
    """
    Central registry for data providers.
    
    Manages provider instances and provides access by name or type.
    """
    
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}
        self._provider_classes: dict[str, Type[BaseProvider]] = {}
    
    def register_class(self, provider_class: Type[BaseProvider]) -> None:
        """
        Register a provider class (for lazy instantiation).
        
        Args:
            provider_class: The provider class to register
        """
        # Create a temporary instance to get the name
        # In practice, you'd use a class attribute or decorator
        name = provider_class.__name__.lower().replace("provider", "")
        self._provider_classes[name] = provider_class
        logger.debug(f"Registered provider class: {name}")
    
    def register(self, provider: BaseProvider) -> None:
        """
        Register a provider instance.
        
        Args:
            provider: The provider instance to register
        """
        if provider.name in self._providers:
            logger.warning(f"Overwriting existing provider: {provider.name}")
        
        self._providers[provider.name] = provider
        logger.info(f"Registered provider: {provider.name} ({provider.provider_type.value})")
    
    def unregister(self, name: str) -> None:
        """
        Unregister a provider.
        
        Args:
            name: Provider name to unregister
        """
        if name in self._providers:
            del self._providers[name]
            logger.info(f"Unregistered provider: {name}")
    
    def get(self, name: str) -> BaseProvider:
        """
        Get a provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            Provider instance
            
        Raises:
            ConfigurationError: If provider not found
        """
        if name not in self._providers:
            raise ConfigurationError(
                f"Provider not found: {name}",
                details={"available": list(self._providers.keys())},
            )
        return self._providers[name]
    
    def get_optional(self, name: str) -> Optional[BaseProvider]:
        """
        Get a provider by name, returning None if not found.
        
        Args:
            name: Provider name
            
        Returns:
            Provider instance or None
        """
        return self._providers.get(name)
    
    def get_all(self) -> list[BaseProvider]:
        """
        Get all registered providers.
        
        Returns:
            List of all provider instances
        """
        return list(self._providers.values())
    
    def get_active(self) -> list[BaseProvider]:
        """
        Get all enabled providers.
        
        Returns:
            List of enabled provider instances
        """
        return [p for p in self._providers.values() if p.is_enabled]
    
    def get_by_type(self, provider_type: ProviderType) -> list[BaseProvider]:
        """
        Get all providers of a specific type.
        
        Args:
            provider_type: Type to filter by
            
        Returns:
            List of matching providers
        """
        return [
            p for p in self._providers.values()
            if p.provider_type == provider_type
        ]
    
    def get_names(self) -> list[str]:
        """
        Get names of all registered providers.
        
        Returns:
            List of provider names
        """
        return list(self._providers.keys())
    
    def has(self, name: str) -> bool:
        """
        Check if a provider is registered.
        
        Args:
            name: Provider name
            
        Returns:
            True if registered
        """
        return name in self._providers
    
    async def initialize_all(self) -> None:
        """Initialize all registered providers."""
        for provider in self._providers.values():
            try:
                await provider.initialize()
                logger.info(f"Initialized provider: {provider.name}")
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider.name}", error=str(e))
                raise
    
    async def close_all(self) -> None:
        """Close all registered providers."""
        for provider in self._providers.values():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider {provider.name}", error=str(e))
    
    def __len__(self) -> int:
        return len(self._providers)
    
    def __contains__(self, name: str) -> bool:
        return name in self._providers
    
    def __iter__(self):
        return iter(self._providers.values())


# Global registry instance
_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """
    Get the global provider registry.
    
    Returns:
        ProviderRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def reset_provider_registry() -> None:
    """Reset the global provider registry."""
    global _registry
    _registry = None


async def setup_providers() -> ProviderRegistry:
    """
    Set up and initialize all configured providers.
    
    Returns:
        Configured ProviderRegistry
    """
    from atlas.providers.tiingo import TiingoProvider
    from atlas.providers.fred import FredProvider
    
    settings = get_settings()
    registry = get_provider_registry()
    
    # Register Tiingo if enabled
    if settings.providers.tiingo.enabled:
        tiingo = TiingoProvider()
        registry.register(tiingo)
    
    # Register FRED if enabled
    if settings.providers.fred.enabled:
        fred = FredProvider()
        registry.register(fred)
    
    # Initialize all providers
    await registry.initialize_all()
    
    logger.info(f"Initialized {len(registry)} providers")
    return registry
