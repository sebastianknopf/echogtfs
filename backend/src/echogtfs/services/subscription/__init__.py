from echogtfs.services.subscription.intf_siri_subscription_service import SiriSubscriptionServiceInterface
from echogtfs.services.subscription.siri_subscription_service import SiriSubscriptionService

_siri_subscription_service: SiriSubscriptionServiceInterface | None = None


def set_siri_subscription_service(service: SiriSubscriptionServiceInterface) -> None:
    """Register the application-wide SIRI subscription service."""
    global _siri_subscription_service
    _siri_subscription_service = service


def get_siri_subscription_service() -> SiriSubscriptionServiceInterface:
    """Return the configured SIRI subscription service."""
    if _siri_subscription_service is None:
        raise RuntimeError("SIRI subscription service is not initialized")

    return _siri_subscription_service


__all__ = [
    "SiriSubscriptionService",
    "SiriSubscriptionServiceInterface",
    "set_siri_subscription_service",
    "get_siri_subscription_service",
]
