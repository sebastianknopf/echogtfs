"""
Data source adapters for importing service alerts from external systems.

Each adapter implements the BaseAdapter interface and provides:
- Configuration validation
- Data fetching from external endpoints
- Transformation to ServiceAlert database structure
"""

from echogtfs.services.adapters.base import BaseAdapter
from echogtfs.services.adapters.sirilite import SiriLiteAdapter
from echogtfs.services.adapters.gtfsrt import GtfsRtAdapter

__all__ = [
    "BaseAdapter",
    "SiriLiteAdapter",
    "GtfsRtAdapter",
]


# Registry mapping adapter type names to adapter classes
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "sirilite": SiriLiteAdapter,
    "gtfsrt": GtfsRtAdapter,
}


def get_adapter(adapter_type: str, config: dict) -> BaseAdapter:
    """
    Factory function to create an adapter instance by type.
    
    Args:
        adapter_type: Type of adapter ("sirilite", "gtfsrt", etc.)
        config: Configuration dictionary for the adapter
        
    Returns:
        Instantiated adapter
        
    Raises:
        ValueError: If adapter type is not registered
    """
    adapter_class = ADAPTER_REGISTRY.get(adapter_type.lower())
    if not adapter_class:
        raise ValueError(
            f"Unknown adapter type: {adapter_type}. "
            f"Available types: {', '.join(ADAPTER_REGISTRY.keys())}"
        )
    
    return adapter_class(config)
