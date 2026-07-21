from __future__ import annotations

from echogtfs.services.database.gtfs_repository import GtfsRepository
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_realtime_repository import RealtimeRepositoryInterface
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.database.realtime_repository import RealtimeRepository
from echogtfs.services.database.system_repository import SystemRepository

_repository: SystemRepositoryInterface | None = None
_gtfs_repository: GtfsRepositoryInterface | None = None
_realtime_repository: RealtimeRepositoryInterface | None = None


def set_system_repository(repository: SystemRepositoryInterface) -> None:
	"""Register the repository singleton for application-wide database access."""
	global _repository
	_repository = repository


def set_gtfs_repository(repository: GtfsRepositoryInterface) -> None:
	"""Register the GTFS repository singleton for GTFS static-table access."""
	global _gtfs_repository
	_gtfs_repository = repository


def set_realtime_repository(repository: RealtimeRepositoryInterface) -> None:
	"""Register the realtime repository singleton for realtime-table access."""
	global _realtime_repository
	_realtime_repository = repository


def get_system_repository() -> SystemRepositoryInterface:
	"""Return the configured repository singleton."""
	if _repository is None:
		raise RuntimeError("Repository is not initialized")
	return _repository


def get_gtfs_repository() -> GtfsRepositoryInterface:
	"""Return the configured GTFS repository singleton."""
	if _gtfs_repository is None:
		raise RuntimeError("GTFS repository is not initialized")
	return _gtfs_repository


def get_realtime_repository() -> RealtimeRepositoryInterface:
	"""Return the configured realtime repository singleton."""
	if _realtime_repository is None:
		raise RuntimeError("Realtime repository is not initialized")
	return _realtime_repository


__all__ = [
	"SystemRepositoryInterface",
	"RealtimeRepositoryInterface",
	"GtfsRepositoryInterface",
	"SystemRepository",
	"RealtimeRepository",
	"GtfsRepository",
	"set_system_repository",
	"set_realtime_repository",
	"set_gtfs_repository",
	"get_system_repository",
	"get_realtime_repository",
	"get_gtfs_repository",
]
