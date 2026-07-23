from enum import Enum


class InvalidReferencePolicy(str, Enum):
    """Policy for handling objects with invalid entity references."""

    DISCARD_ENTIRE_OBJECT = "discard_entire_object"  # Discard entire object if any reference is invalid
    KEEP_OBJECT_DISABLED = "keep_object_disabled"  # Keep entire object but deactivate it when references are invalid
    DISCARD_INVALID = "discard_invalid"  # Discard only invalid references, keep object
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


class ExpiredRealtimeObjectPolicy(str, Enum):
    """Policy for handling expired alerts during cleanup."""

    DEACTIVATE = "deactivate"  # Set is_active=False for expired alerts
    DELETE = "delete"  # Delete expired alerts from database
