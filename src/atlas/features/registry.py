"""Feature registry for managing feature definitions."""

from functools import lru_cache
from typing import Optional, Type

from atlas.core.exceptions import ConfigurationError
from atlas.core.logging import get_logger
from atlas.features.base import (
    BaseFeature,
    CumulativeReturn,
    DailyReturn,
    LogReturn,
    RealizedVolatility,
    RSI,
    SimpleMovingAverage,
)

logger = get_logger(__name__)


class FeatureRegistry:
    """
    Central registry for feature definitions.
    
    Manages feature instances and resolves calculation order based on dependencies.
    """
    
    def __init__(self) -> None:
        self._features: dict[str, BaseFeature] = {}
        self._dependency_graph: dict[str, list[str]] = {}
    
    def register(self, feature: BaseFeature) -> None:
        """
        Register a feature.
        
        Args:
            feature: Feature instance to register
        """
        if feature.name in self._features:
            logger.warning(f"Overwriting existing feature: {feature.name}")
        
        self._features[feature.name] = feature
        self._dependency_graph[feature.name] = feature.dependencies
        
        logger.debug(f"Registered feature: {feature.name}")
    
    def unregister(self, name: str) -> None:
        """
        Unregister a feature.
        
        Args:
            name: Feature name to unregister
        """
        if name in self._features:
            del self._features[name]
            del self._dependency_graph[name]
    
    def get(self, name: str) -> BaseFeature:
        """
        Get a feature by name.
        
        Args:
            name: Feature name
            
        Returns:
            Feature instance
            
        Raises:
            ConfigurationError: If feature not found
        """
        if name not in self._features:
            raise ConfigurationError(
                f"Feature not found: {name}",
                details={"available": list(self._features.keys())},
            )
        return self._features[name]
    
    def get_optional(self, name: str) -> Optional[BaseFeature]:
        """
        Get a feature by name, returning None if not found.
        
        Args:
            name: Feature name
            
        Returns:
            Feature instance or None
        """
        return self._features.get(name)
    
    def get_all(self) -> list[BaseFeature]:
        """
        Get all registered features.
        
        Returns:
            List of all feature instances
        """
        return list(self._features.values())
    
    def get_by_category(self, category: str) -> list[BaseFeature]:
        """
        Get all features in a category.
        
        Args:
            category: Category to filter by
            
        Returns:
            List of matching features
        """
        return [f for f in self._features.values() if f.category == category]
    
    def get_names(self) -> list[str]:
        """
        Get names of all registered features.
        
        Returns:
            List of feature names
        """
        return list(self._features.keys())
    
    def has(self, name: str) -> bool:
        """
        Check if a feature is registered.
        
        Args:
            name: Feature name
            
        Returns:
            True if registered
        """
        return name in self._features
    
    def get_calculation_order(
        self,
        feature_names: Optional[list[str]] = None,
    ) -> list[BaseFeature]:
        """
        Get features in dependency-resolved order.
        
        Uses topological sort to ensure features are calculated after their dependencies.
        
        Args:
            feature_names: Optional list of specific features to order.
                          If None, returns all features in order.
                          
        Returns:
            List of features in calculation order
        """
        if feature_names is None:
            feature_names = list(self._features.keys())
        
        # Build dependency subgraph for requested features
        to_process = set(feature_names)
        processed = set()
        order = []
        
        # Include dependencies
        while to_process:
            current = to_process.pop()
            
            if current in processed:
                continue
            
            # Check dependencies
            deps = self._dependency_graph.get(current, [])
            feature_deps = [d for d in deps if d in self._features]
            
            unprocessed_deps = [d for d in feature_deps if d not in processed]
            
            if unprocessed_deps:
                # Add current back and process dependencies first
                to_process.add(current)
                to_process.update(unprocessed_deps)
            else:
                # All dependencies processed, add to order
                processed.add(current)
                if current in self._features:
                    order.append(self._features[current])
        
        return order
    
    def get_required_lookback(
        self,
        feature_names: Optional[list[str]] = None,
    ) -> int:
        """
        Get the maximum lookback required for a set of features.
        
        Args:
            feature_names: Features to check. If None, checks all.
            
        Returns:
            Maximum lookback days required
        """
        if feature_names is None:
            features = self._features.values()
        else:
            features = [self._features[n] for n in feature_names if n in self._features]
        
        if not features:
            return 0
        
        return max(f.lookback_days for f in features)
    
    def get_required_columns(
        self,
        feature_names: Optional[list[str]] = None,
    ) -> set[str]:
        """
        Get all required data columns for a set of features.
        
        Args:
            feature_names: Features to check. If None, checks all.
            
        Returns:
            Set of required column names
        """
        if feature_names is None:
            features = self._features.values()
        else:
            features = [self._features[n] for n in feature_names if n in self._features]
        
        columns = set()
        for feature in features:
            for dep in feature.dependencies:
                # If dependency is not a feature, it's a data column
                if dep not in self._features:
                    columns.add(dep)
        
        return columns
    
    def __len__(self) -> int:
        return len(self._features)
    
    def __contains__(self, name: str) -> bool:
        return name in self._features
    
    def __iter__(self):
        return iter(self._features.values())


# Global registry instance
_registry: Optional[FeatureRegistry] = None


def get_feature_registry() -> FeatureRegistry:
    """
    Get the global feature registry.
    
    Returns:
        FeatureRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = FeatureRegistry()
        _register_default_features(_registry)
    return _registry


def reset_feature_registry() -> None:
    """Reset the global feature registry."""
    global _registry
    _registry = None


def _register_default_features(registry: FeatureRegistry) -> None:
    """Register the default set of features."""
    
    # Returns
    registry.register(DailyReturn())
    registry.register(LogReturn())
    registry.register(CumulativeReturn(window=5))
    registry.register(CumulativeReturn(window=21))
    registry.register(CumulativeReturn(window=63))
    registry.register(CumulativeReturn(window=126))
    registry.register(CumulativeReturn(window=252))
    
    # Volatility
    registry.register(RealizedVolatility(window=21))
    registry.register(RealizedVolatility(window=63))
    
    # Momentum
    registry.register(SimpleMovingAverage(window=20))
    registry.register(SimpleMovingAverage(window=50))
    registry.register(SimpleMovingAverage(window=200))
    registry.register(RSI(window=14))
    
    logger.info(f"Registered {len(registry)} default features")
