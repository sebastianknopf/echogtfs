from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.enrichment.entity_enrichtment_service import EntityEnrichmentService


class TestEntityEnrichmentService(unittest.IsolatedAsyncioTestCase):
    async def test_apply_enrichment_async_matches_patterns(self):
        service = EntityEnrichmentService()
        service._enrichments = [
            {
                "enrichment_type": "cause",
                "source_field": "header",
                "key": "*signal*",
                "value": "TECHNICAL_PROBLEM",
            },
            {
                "enrichment_type": "severity",
                "source_field": "description",
                "key": "*major*",
                "value": "SEVERE",
            },
        ]

        alert = {
            "id": "1",
            "cause": "UNKNOWN_CAUSE",
            "effect": "UNKNOWN_EFFECT",
            "severity_level": "UNKNOWN_SEVERITY",
            "translations": [{"header_text": "Signal issue", "description_text": "major delay"}],
        }
        await service.apply_enrichment_async(alert, "adapter")

        self.assertEqual(alert["cause"], "TECHNICAL_PROBLEM")
        self.assertEqual(alert["severity_level"], "SEVERE")