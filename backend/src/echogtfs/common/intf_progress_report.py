from __future__ import annotations

from abc import ABC, abstractmethod


class ReportProgressInterface(ABC):
    """Interface for reporting progress of long-running operations."""

    @abstractmethod
    async def report_progress(self, *, progress: float, message: str) -> dict[str, str | float]:
        """Report progress of a long-running operation.

        Args:
            progress (float): Progress value between 0.0 and 1.0.
            message (str): Message describing the current progress.
        """
        raise NotImplementedError