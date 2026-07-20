from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources import get_datasource


class TestDatasourceRegistry(unittest.TestCase):
    def test_get_datasource_returns_expected_instance(self):
        self.assertEqual(
            get_datasource("gtfsrt", {"endpoint": "https://x", "dialect": "gtfsrt-servicealerts"}).get_datasource_type(),
            "gtfsrt",
        )
        self.assertEqual(
            get_datasource("sirilite", {"endpoint": "https://x", "dialect": "swiss"}).get_datasource_type(),
            "sirilite",
        )
        self.assertEqual(
            get_datasource(
                "sirisx",
                {
                    "endpoint": "https://x/{participantRef}",
                    "participantref": "P1",
                    "method": "request/response",
                    "dialect": "sirisx",
                },
            ).get_datasource_type(),
            "sirisx",
        )

    def test_get_datasource_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            get_datasource("missing", {})