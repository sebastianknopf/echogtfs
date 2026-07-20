from __future__ import annotations

from echogtfs.services.database.gtfs_repository import GtfsRepository
from echogtfs.services.database.intf_gtfs_repository import GtfsRepositoryInterface
from echogtfs.services.database.intf_repository import RepositoryInterface
from echogtfs.services.database.sqlalchemy_repository import SqlAlchemyRepository

_repository: RepositoryInterface | None = None
_gtfs_repository: GtfsRepositoryInterface | None = None


def set_repository(repository: RepositoryInterface) -> None:
	"""Register the repository singleton for application-wide database access."""
	global _repository
	_repository = repository


def set_gtfs_repository(repository: GtfsRepositoryInterface) -> None:
	"""Register the GTFS repository singleton for GTFS static-table access."""
	global _gtfs_repository
	_gtfs_repository = repository


def get_repository() -> RepositoryInterface:
	"""Return the configured repository singleton."""
	if _repository is None:
		raise RuntimeError("Repository is not initialized")
	return _repository


def get_gtfs_repository() -> GtfsRepositoryInterface:
	"""Return the configured GTFS repository singleton."""
	if _gtfs_repository is None:
		raise RuntimeError("GTFS repository is not initialized")
	return _gtfs_repository


__all__ = [
	"RepositoryInterface",
	"GtfsRepositoryInterface",
	"SqlAlchemyRepository",
	"GtfsRepository",
	"set_repository",
	"set_gtfs_repository",
	"get_repository",
	"get_gtfs_repository",
]
