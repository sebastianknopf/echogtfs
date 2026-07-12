from __future__ import annotations

from abc import ABC, abstractmethod


class GtfsRealtimeExportInterface(ABC):
    """Interface for GTFS-Realtime export services."""

    @abstractmethod
    async def export_protobuf(self) -> bytes:
        """Export GTFS-Realtime payload as protobuf bytes."""
        raise NotImplementedError

    @abstractmethod
    async def export_json(self) -> bytes:
        """Export GTFS-Realtime payload as JSON bytes."""
        raise NotImplementedError
