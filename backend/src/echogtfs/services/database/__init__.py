from __future__ import annotations

from echogtfs.services.database.intf_repository import RepositoryInterface
from echogtfs.services.database.sqlalchemy_repository import SqlAlchemyRepository

_repository: RepositoryInterface | None = None


def set_repository(repository: RepositoryInterface) -> None:
	"""Register the repository singleton for application-wide database access."""
	global _repository
	_repository = repository


def get_repository() -> RepositoryInterface:
	"""Return the configured repository singleton."""
	if _repository is None:
		raise RuntimeError("Repository is not initialized")
	return _repository


__all__ = [
	"RepositoryInterface",
	"SqlAlchemyRepository",
	"set_repository",
	"get_repository",
]
