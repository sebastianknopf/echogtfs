from enum import Enum


class AlertCause(str, Enum):
    """GTFS-RT Alert cause enum."""

    UNKNOWN_CAUSE = "UNKNOWN_CAUSE"
    OTHER_CAUSE = "OTHER_CAUSE"
    TECHNICAL_PROBLEM = "TECHNICAL_PROBLEM"
    STRIKE = "STRIKE"
    DEMONSTRATION = "DEMONSTRATION"
    ACCIDENT = "ACCIDENT"
    HOLIDAY = "HOLIDAY"
    WEATHER = "WEATHER"
    MAINTENANCE = "MAINTENANCE"
    CONSTRUCTION = "CONSTRUCTION"
    POLICE_ACTIVITY = "POLICE_ACTIVITY"
    MEDICAL_EMERGENCY = "MEDICAL_EMERGENCY"


class AlertEffect(str, Enum):
    """GTFS-RT Alert effect enum."""

    NO_SERVICE = "NO_SERVICE"
    REDUCED_SERVICE = "REDUCED_SERVICE"
    SIGNIFICANT_DELAYS = "SIGNIFICANT_DELAYS"
    DETOUR = "DETOUR"
    ADDITIONAL_SERVICE = "ADDITIONAL_SERVICE"
    MODIFIED_SERVICE = "MODIFIED_SERVICE"
    OTHER_EFFECT = "OTHER_EFFECT"
    UNKNOWN_EFFECT = "UNKNOWN_EFFECT"
    STOP_MOVED = "STOP_MOVED"
    NO_EFFECT = "NO_EFFECT"
    ACCESSIBILITY_ISSUE = "ACCESSIBILITY_ISSUE"


class AlertSeverityLevel(str, Enum):
    """GTFS-RT Alert severity level enum (SeverityLevel)."""

    UNKNOWN_SEVERITY = "UNKNOWN_SEVERITY"
    INFO = "INFO"
    WARNING = "WARNING"
    SEVERE = "SEVERE"


class PeriodType(str, Enum):
    """Type of validity period for service alerts."""

    IMPACT_PERIOD = "impact_period"  # Actual validity period (when alert affects service)
    COMMUNICATION_PERIOD = "communication_period"  # Publication period (when alert should be shown)


class AssignmentType(str, Enum):
    """How a realtime entity was assigned to a nominal trip."""

    DIRECT_BY_ID = "DIRECT_BY_ID"
    MATCHED_BY_START_STOP = "MATCHED_BY_START_STOP"
    MATCHED_BY_CURRENT_STOP = "MATCHED_BY_CURRENT_STOP"
    NO_MATCH_GENERAL = "NO_MATCH_GENERAL"
    NO_MATCH_AMBIGUOUS_TRIP = "NO_MATCH_AMBIGUOUS_TRIP"


class CongestionLevel(str, Enum):
    """GTFS-RT congestion level enum (VehiclePosition.CongestionLevel)."""

    UNKNOWN_CONGESTION_LEVEL = "UNKNOWN_CONGESTION_LEVEL"
    RUNNING_SMOOTHLY = "RUNNING_SMOOTHLY"
    STOP_AND_GO = "STOP_AND_GO"
    CONGESTION = "CONGESTION"
    SEVERE_CONGESTION = "SEVERE_CONGESTION"


class VehicleStopStatus(str, Enum):
    """GTFS-RT vehicle stop status enum (VehiclePosition.VehicleStopStatus)."""

    INCOMING_AT = "INCOMING_AT"
    STOPPED_AT = "STOPPED_AT"
    IN_TRANSIT_TO = "IN_TRANSIT_TO"


class WheelchairAccessible(str, Enum):
    """GTFS-RT wheelchair accessibility enum."""

    NO_VALUE = "NO_VALUE"
    UNKNOWN = "UNKNOWN"
    WHEELCHAIR_ACCESSIBLE = "WHEELCHAIR_ACCESSIBLE"
    WHEELCHAIR_INACCESSIBLE = "WHEELCHAIR_INACCESSIBLE"


__all__ = [
    "AlertCause",
    "AlertEffect",
    "AlertSeverityLevel",
    "PeriodType",
    "AssignmentType",
    "CongestionLevel",
    "VehicleStopStatus",
    "WheelchairAccessible",
]
