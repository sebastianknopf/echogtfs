from enum import Enum


class InvalidReferencePolicy(str, Enum):
    """Policy for handling alerts with invalid entity references."""

    DISCARD_ALERT = "discard_alert"  # Discard entire alert if any reference is invalid
    KEEP_ALERT = "keep_alert"  # Keep entire alert even if references are invalid
    DISCARD_INVALID = "discard_invalid"  # Discard only invalid references, keep alert
    DISCARD_INVALID_ELEMENTS = "discard_invalid_elements"  # Discard invalid fields within references
    NOT_SPECIFIED = "not_specified"  # No specific policy defined


class EnrichmentType(str, Enum):
    """Type of enrichment that can be extracted from alert text."""

    CAUSE = "cause"
    EFFECT = "effect"
    SEVERITY = "severity"


class SourceField(str, Enum):
    """Source field to extract enrichment values from."""

    HEADER = "header"
    DESCRIPTION = "description"
    HEADER_DESCRIPTION = "header_description"  # Match in either header or description


class ExpiredAlertPolicy(str, Enum):
    """Policy for handling expired alerts during cleanup."""

    DEACTIVATE = "deactivate"  # Set is_active=False for expired alerts
    DELETE = "delete"  # Delete expired alerts from database
