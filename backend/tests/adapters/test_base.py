"""
Unit tests for BaseAdapter class.

Tests the abstract base class functionality that all adapters inherit.
"""

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

# Setup test environment before importing echogtfs
from tests.test_config import setup_test_environment
setup_test_environment()

from echogtfs.services.adapters.base import BaseAdapter


class ConcreteAdapter(BaseAdapter):
    """Concrete implementation for testing."""
    
    CONFIG_SCHEMA = [
        {
            "name": "endpoint",
            "type": "url",
            "label": "test.endpoint.label",
            "required": True,
            "placeholder": "http://example.com",
            "help_text": "Test endpoint",
        }
    ]
    
    def _validate_config(self) -> None:
        if "endpoint" not in self.config:
            raise ValueError("endpoint is required")
    
    async def fetch_alerts(self):
        return []


class TestBaseAdapter(unittest.TestCase):
    """Test BaseAdapter abstract base class."""
    
    def test_adapter_instantiation_with_valid_config(self):
        """Test that adapter can be instantiated with valid config."""
        config = {"endpoint": "http://example.com"}
        adapter = ConcreteAdapter(config)
        self.assertEqual(adapter.config, config)
    
    def test_adapter_instantiation_with_invalid_config(self):
        """Test that adapter validation catches invalid config."""
        config = {}
        with self.assertRaises(ValueError) as context:
            ConcreteAdapter(config)
        self.assertIn("endpoint is required", str(context.exception))
    
    def test_is_uuid_valid(self):
        """Test UUID validation with valid UUID."""
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        valid_uuid = str(uuid.uuid4())
        self.assertTrue(adapter._is_uuid(valid_uuid))
    
    def test_is_uuid_invalid(self):
        """Test UUID validation with invalid UUID."""
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        self.assertFalse(adapter._is_uuid("not-a-uuid"))
        self.assertFalse(adapter._is_uuid(""))
        self.assertFalse(adapter._is_uuid("123"))
    
    def test_make_unique_id_from_uuid(self):
        """Test that existing UUIDs are preserved."""
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        original_uuid = str(uuid.uuid4())
        result = adapter._make_unique_id(original_uuid, "test_source")
        self.assertEqual(str(result), original_uuid)
    
    def test_make_unique_id_from_string(self):
        """Test that non-UUID strings generate deterministic UUIDs."""
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        
        # Same input should generate same UUID
        id1 = adapter._make_unique_id("alert-123", "test_source")
        id2 = adapter._make_unique_id("alert-123", "test_source")
        self.assertEqual(id1, id2)
        
        # Different source should generate different UUID
        id3 = adapter._make_unique_id("alert-123", "other_source")
        self.assertNotEqual(id1, id3)
        
        # Different ID should generate different UUID
        id4 = adapter._make_unique_id("alert-456", "test_source")
        self.assertNotEqual(id1, id4)
    
    def test_get_adapter_type(self):
        """Test that adapter type is correctly extracted from class name."""
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        self.assertEqual(adapter.get_adapter_type(), "concrete")
    
    def test_get_config_schema(self):
        """Test that config schema is returned correctly."""
        schema = ConcreteAdapter.get_config_schema()
        self.assertEqual(len(schema), 1)
        self.assertEqual(schema[0]["name"], "endpoint")
        self.assertEqual(schema[0]["type"], "url")
        self.assertEqual(schema[0]["required"], True)


class TestBaseAdapterAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for BaseAdapter."""
    
    async def test_fetch_alerts_abstract(self):
        """Test that fetch_alerts must be implemented by subclasses."""
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        alerts = await adapter.fetch_alerts()
        self.assertEqual(alerts, [])
    
    @patch('echogtfs.services.adapters.base.select')
    async def test_load_mappings(self, mock_select):
        """Test loading mappings from database."""
        from tests.helpers import MockAsyncSession
        
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        db = MockAsyncSession()
        
        # Mock database response
        mock_mapping1 = MagicMock()
        mock_mapping1.entity_type = "route"
        mock_mapping1.key = "ext_route_1"
        mock_mapping1.value = "gtfs_route_1"
        
        mock_mapping2 = MagicMock()
        mock_mapping2.entity_type = "route"
        mock_mapping2.key = "ext_route_2"
        mock_mapping2.value = "gtfs_route_2"
        
        mock_mapping3 = MagicMock()
        mock_mapping3.entity_type = "agency"
        mock_mapping3.key = "ext_agency_1"
        mock_mapping3.value = "gtfs_agency_1"
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_mapping1, mock_mapping2, mock_mapping3
        ]
        db.execute.return_value = mock_result
        
        # Test
        mappings = await adapter._load_mappings(db, source_id=1)
        
        # Verify structure
        self.assertIn("route", mappings)
        self.assertIn("agency", mappings)
        self.assertEqual(mappings["route"]["ext_route_1"], "gtfs_route_1")
        self.assertEqual(mappings["route"]["ext_route_2"], "gtfs_route_2")
        self.assertEqual(mappings["agency"]["ext_agency_1"], "gtfs_agency_1")
    
    @patch('echogtfs.services.adapters.base.select')
    async def test_load_enrichments(self, mock_select):
        """Test loading enrichments from database."""
        from tests.helpers import MockAsyncSession
        
        adapter = ConcreteAdapter({"endpoint": "http://example.com"})
        db = MockAsyncSession()
        
        # Mock database response
        mock_enrichment1 = MagicMock()
        mock_enrichment1.enrichment_type = "inject"
        mock_enrichment1.source_field = "route_id"
        mock_enrichment1.key = "pattern"
        mock_enrichment1.value = "123"
        mock_enrichment1.sort_order = 1
        
        mock_enrichment2 = MagicMock()
        mock_enrichment2.enrichment_type = "replace"
        mock_enrichment2.source_field = "stop_id"
        mock_enrichment2.key = "old"
        mock_enrichment2.value = "new"
        mock_enrichment2.sort_order = 2
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_enrichment1, mock_enrichment2
        ]
        db.execute.return_value = mock_result
        
        # Test
        enrichments = await adapter._load_enrichments(db, source_id=1)
        
        # Verify
        self.assertEqual(len(enrichments), 2)
        self.assertEqual(enrichments[0]["enrichment_type"], "inject")
        self.assertEqual(enrichments[1]["enrichment_type"], "replace")



if __name__ == '__main__':
    unittest.main()
