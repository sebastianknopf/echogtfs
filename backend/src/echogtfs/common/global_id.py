from __future__ import annotations

import re

from echogtfs.common.config import settings


class GlobalId:
    """Encapsules helper methods for working with global IDs in public transport."""

    @staticmethod
    def is_global_id(input: str) -> bool:
        """Returns True if input is a global ID."""

        if input is None:
            return False

        # try first against the configured pattern
        pattern: str | None = settings.global_id_pattern
        if pattern is not None and not re.fullmatch(pattern, input):
            return False

        # fallback is the internal implementation
        parts: list[str] = input.split(":")
        if len(parts) < 3:
            return False

        if not parts[0].isalpha():
            return False

        return all(part.strip() for part in parts[:3]) and all(" " not in part for part in parts)
    
    @staticmethod
    def level(input: str, level: int) -> str:
        """Returns the reduced global ID to the desired level. If input is no global ID, input is returned again."""
        
        if not GlobalId.is_global_id(input):
            return input
        
        if level < 1:
            raise ValueError("Level for reducing a global ID must be at least 1!")
        
        splitted: list[str] = input.split(":")
        return ":".join(splitted[:level])
    