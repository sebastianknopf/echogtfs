from __future__ import annotations

from collections.abc import Iterable

from echogtfs.services.caching.intf_caching_service import CachingServiceInterface
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface


class GtfsIdValidator:
    """Per-run validator for nominal GTFS IDs backed by the Redis ID cache.

    IDs are checked in bulk via prefetch(); the confirmed ones are exposed through
    valid_ids() so synchronous validation helpers can keep using plain set lookups.
    Nominal trip IDs use the same cache; only trip matching queries the database directly.
    """

    def __init__(self, caching_service: CachingServiceInterface, gtfs_repository: GtfsRepositoryInterface):
        self._caching_service = caching_service
        self._gtfs_repository = gtfs_repository
        self._checked: dict[str, set[str]] = {}
        self._valid: dict[str, set[str]] = {}

    async def prefetch(self, kind: str, gtfs_ids: Iterable[object]) -> None:
        """Check all not yet checked IDs of one kind with a single cache round trip."""
        checked = self._checked.setdefault(kind, set())
        valid = self._valid.setdefault(kind, set())

        pending = sorted({str(gtfs_id) for gtfs_id in gtfs_ids if gtfs_id} - checked)
        if not pending:
            return

        known_ids = await self._caching_service.contains_gtfs_ids(kind, pending)
        if known_ids is None:
            await self._caching_service.rebuild_gtfs_ids(self._gtfs_repository, force=False)
            known_ids = await self._caching_service.contains_gtfs_ids(kind, pending)
            if known_ids is None:
                raise RuntimeError("GTFS ID cache is not available after rebuild")

        checked.update(pending)
        valid.update(known_ids)

    def valid_ids(self) -> dict[str, set[str]]:
        """Return the confirmed IDs per kind; IDs that were never prefetched count as unknown."""
        return {
            "agency": self._valid.get("agency", set()),
            "route": self._valid.get("route", set()),
            "stop": self._valid.get("stop", set()),
            "trip": self._valid.get("trip", set()),
        }
