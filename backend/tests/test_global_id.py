from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Ensure settings can be constructed from environment during test imports.
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.common.global_id import GlobalId


class TestGlobalId(unittest.TestCase):
    def test_is_global_id_true_for_valid_default_format(self):
        self.assertTrue(GlobalId.is_global_id("de:agency:trip"))

    def test_is_global_id_false_for_none(self):
        self.assertFalse(GlobalId.is_global_id(None))

    def test_is_global_id_false_for_invalid_default_format(self):
        self.assertFalse(GlobalId.is_global_id("de:agency"))
        self.assertFalse(GlobalId.is_global_id("123:agency:trip"))
        self.assertFalse(GlobalId.is_global_id("de:agency:trip id"))

    def test_is_global_id_uses_configured_pattern(self):
        with patch(
            "echogtfs.common.global_id.settings.global_id_pattern",
            r"de:[a-z]+:[a-z]+",
            create=True,
        ):
            self.assertTrue(GlobalId.is_global_id("de:agency:trip"))
            self.assertFalse(GlobalId.is_global_id("ch:agency:trip"))

    def test_level_reduces_to_requested_level_for_valid_global_id(self):
        self.assertEqual(GlobalId.level("de:agency:trip:variant", 3), "de:agency:trip")

    def test_level_returns_input_for_non_global_id(self):
        self.assertEqual(GlobalId.level("not-a-global-id", 2), "not-a-global-id")

    def test_level_raises_for_invalid_level(self):
        with self.assertRaises(ValueError):
            GlobalId.level("de:agency:trip", 0)
