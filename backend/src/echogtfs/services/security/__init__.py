from __future__ import annotations

from echogtfs.services.security.intf_security_service import SecurityServiceInterface
from echogtfs.services.security.security_service import SecurityService

_security_service: SecurityServiceInterface | None = None


def set_security_service(security_service: SecurityServiceInterface) -> None:
    """Register the security service singleton for application-wide access."""
    global _security_service
    _security_service = security_service


def get_security_service() -> SecurityServiceInterface:
    """Return the configured security service singleton."""
    if _security_service is None:
        raise RuntimeError("Security service is not initialized")

    return _security_service


__all__ = [
    "SecurityServiceInterface",
    "SecurityService",
    "set_security_service",
    "get_security_service",
]