from abc import ABC
import re
from typing import Any


class TransformerBase(ABC):
    """
    Abstract base class for transformers.
    
    Each transformer handles the transformation of external data into the internal data model.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def get_filters(self) -> dict[str, list[str]]:
        """Return configured filters grouped by their known prefixes."""
        filters = {"line": [], "operator": [], "legacy": []}
        configured_filter = self.config.get("filter", "")

        if not configured_filter:
            return filters

        for filter_value in configured_filter.split(","):
            filter_value = filter_value.strip()
            matched_prefix = False
            for filter_type in ("line", "operator"):
                prefix = f"{filter_type}/"
                if filter_value.startswith(prefix):
                    value = filter_value[len(prefix):].strip()
                    if value:
                        filters[filter_type].append(value)
                    matched_prefix = True
                    break

            if not matched_prefix and filter_value:
                filters["legacy"].append(filter_value)

        return filters

    @staticmethod
    def identifier_matches(identifier: str, match: str) -> bool:
        """Match an identifier against a pattern using '*' as a wildcard."""
        regex = re.escape(match).replace(r"\*", ".*")
        return bool(re.fullmatch(regex, identifier))