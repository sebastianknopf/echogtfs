from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.services.mapping.identifier_mapping_service import IdentifierMappingService


class TestIdentifierMappingService(unittest.TestCase):
    def test_identifier_mapping_applies_exact_and_wildcard(self):
        service = IdentifierMappingService()
        service._mappings = {
            "route": {"X1": "R1", "BUS-*": "BUS"},
            "agency": {},
            "stop": {},
        }
        entity = service.apply_mapping({"route_id": "BUS-10"})
        self.assertEqual(entity["route_id"], "BUS")