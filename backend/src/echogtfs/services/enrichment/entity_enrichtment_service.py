from __future__ import annotations

import logging
import re
from typing import Any

from echogtfs.enum.system import EnrichmentType, SourceField
from echogtfs.services.database.intf_system_repository import SystemRepositoryInterface
from echogtfs.services.enrichment.intf_entity_enrichment import EntityEnrichmentInterface

logger = logging.getLogger("uvicorn")


class EntityEnrichmentService(EntityEnrichmentInterface):
    """Service for loading and applying datasource entity enrichment rules."""

    def __init__(self) -> None:
        self._enrichments: list[dict[str, Any]] = []

    async def initialize(
        self,
        repository: SystemRepositoryInterface,
        source_id: int,
    ) -> None:
        """Load enrichment rules for one data source."""
        self._enrichments = await repository.list_data_source_enrichments(source_id)

    def get_loaded_enrichment_count(self) -> int:
        """Return the number of loaded enrichment rules."""
        return len(self._enrichments)

    def apply_enrichment(
        self,
        alert_data: dict[str, Any],
        adapter_type: str,
    ) -> None:
        """Apply loaded enrichment rules in-place to one alert payload."""
        default_values: dict[str, set[str]] = {
            "cause": {"UNKNOWN_CAUSE", "OTHER_CAUSE"},
            "effect": {"UNKNOWN_EFFECT", "OTHER_EFFECT"},
            "severity": {"UNKNOWN_SEVERITY", "INFO"},
        }

        enriched_types: dict[str, bool] = {
            "cause": False,
            "effect": False,
            "severity": False,
        }

        current_cause = str(alert_data.get("cause", "UNKNOWN_CAUSE"))
        current_effect = str(alert_data.get("effect", "UNKNOWN_EFFECT"))
        current_severity = str(alert_data.get("severity_level", "UNKNOWN_SEVERITY"))

        can_enrich_cause = current_cause in default_values["cause"]
        can_enrich_effect = current_effect in default_values["effect"]
        can_enrich_severity = current_severity in default_values["severity"]

        headers: list[str] = []
        descriptions: list[str] = []
        for translation in alert_data.get("translations", []):
            if not isinstance(translation, dict):
                continue

            header_text = translation.get("header_text")
            description_text = translation.get("description_text")

            if isinstance(header_text, str) and header_text:
                headers.append(header_text)
            if isinstance(description_text, str) and description_text:
                descriptions.append(description_text)

        for enrichment in self._enrichments:
            enrichment_type = enrichment["enrichment_type"]
            source_field = enrichment["source_field"]
            pattern = str(enrichment["key"])
            value = str(enrichment["value"])

            if enrichment_type == EnrichmentType.CAUSE:
                if enriched_types["cause"] or not can_enrich_cause:
                    continue
            elif enrichment_type == EnrichmentType.EFFECT:
                if enriched_types["effect"] or not can_enrich_effect:
                    continue
            elif enrichment_type == EnrichmentType.SEVERITY:
                if enriched_types["severity"] or not can_enrich_severity:
                    continue

            texts_to_search: list[str] = []
            if source_field == SourceField.HEADER:
                texts_to_search = headers
            elif source_field == SourceField.DESCRIPTION:
                texts_to_search = descriptions
            elif source_field == SourceField.HEADER_DESCRIPTION:
                texts_to_search = headers + descriptions

            matched = any(
                self._match_enrichment_pattern(text, pattern)
                for text in texts_to_search
            )

            if not matched:
                continue

            if enrichment_type == EnrichmentType.CAUSE:
                alert_data["cause"] = value
                enriched_types["cause"] = True
                logger.debug(
                    f"[{adapter_type}] Enriched record {alert_data['id']}: "
                    f"cause={value} (matched pattern: {pattern})"
                )
            elif enrichment_type == EnrichmentType.EFFECT:
                alert_data["effect"] = value
                enriched_types["effect"] = True
                logger.debug(
                    f"[{adapter_type}] Enriched record {alert_data['id']}: "
                    f"effect={value} (matched pattern: {pattern})"
                )
            elif enrichment_type == EnrichmentType.SEVERITY:
                alert_data["severity_level"] = value
                enriched_types["severity"] = True
                logger.debug(
                    f"[{adapter_type}] Enriched record {alert_data['id']}: "
                    f"severity_level={value} (matched pattern: {pattern})"
                )

            if all(enriched_types.values()):
                break

    def _match_enrichment_pattern(self, text: str, pattern: str) -> bool:
        """Match one enrichment pattern using wildcard and AND-comma semantics."""
        if not text or not pattern:
            return False

        text_lower = text.lower()
        pattern_parts = [part.strip() for part in pattern.split(",") if part.strip()]

        for part in pattern_parts:
            regex_pattern = re.escape(part.lower()).replace(r"\*", ".*")
            regex_pattern = f".*{regex_pattern}.*"
            if not re.search(regex_pattern, text_lower):
                return False

        return True
