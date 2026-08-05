from __future__ import annotations

from echogtfs.services.caching.caching_service import CachingService
from echogtfs.services.caching.intf_caching_service import CachingServiceInterface

_caching_service: CachingServiceInterface | None = None


def set_caching_service(caching_service: CachingServiceInterface) -> None:
    """Register the caching service singleton for application-wide access."""
    global _caching_service
    _caching_service = caching_service


def get_caching_service() -> CachingServiceInterface:
    """Return the configured caching service singleton."""
    if _caching_service is None:
        raise RuntimeError("Caching service is not initialized")

    return _caching_service


__all__ = [
    "CachingServiceInterface",
    "CachingService",
    "set_caching_service",
    "get_caching_service",
]
