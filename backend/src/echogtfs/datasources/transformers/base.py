from abc import ABC
import re


class TransformerBase(ABC):
    """
    Abstract base class for transformers.
    
    Each transformer handles the transformation of external data into the internal data model.
    """

    def __init__(self, filters: dict[str, list[str]]) -> None:
        self._filters = filters

    @staticmethod
    def identifier_matches(identifier: str, match: str) -> bool:
        """Match an identifier against a pattern using '*' as a wildcard."""
        regex = re.escape(match).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, identifier))