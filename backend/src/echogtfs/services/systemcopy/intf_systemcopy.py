from __future__ import annotations

from abc import ABC, abstractmethod

class SystemCopyInterface(ABC):
    """Interface for exporting/importing selected system tables as ZIP archives."""

    @abstractmethod
    async def export_zip(
        self,
        selection: dict[str, bool],
    ) -> bytes:
        """Return a ZIP archive containing manifest.json and selected table JSON files."""
        raise NotImplementedError

    @abstractmethod
    async def import_zip(
        self,
        archive_bytes: bytes,
    ) -> dict[str, object]:
        """Import a ZIP archive and return an operation summary."""
        raise NotImplementedError
