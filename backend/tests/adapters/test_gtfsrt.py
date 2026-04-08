"""
Unit tests for GtfsRtAdapter.

Tests GTFS-Realtime feed parsing and alert transformation.
"""

import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Setup test environment before importing echogtfs
from tests.test_config import setup_test_environment
setup_test_environment()

from echogtfs import gtfs_realtime_pb2
from echogtfs.services.adapters.gtfsrt import GtfsRtAdapter


class TestGtfsRtAdapter(unittest.TestCase):
    """Test GtfsRtAdapter configuration and mapping methods."""
    
    def test_valid_config(self):
        """Test adapter initialization with valid config."""
        config = {
            "endpoint": "https://api.example.com/gtfs-rt",
            "token": "secret-token"
        }
        adapter = GtfsRtAdapter(config)
        self.assertEqual(adapter.config["endpoint"], "https://api.example.com/gtfs-rt")
        self.assertEqual(adapter.config["token"], "secret-token")
    
    def test_config_without_token(self):
        """Test adapter initialization without token (optional)."""
        config = {
            "endpoint": "https://api.example.com/gtfs-rt"
        }
        adapter = GtfsRtAdapter(config)
        self.assertEqual(adapter.config["endpoint"], "https://api.example.com/gtfs-rt")
        self.assertNotIn("token", adapter.config)
    
    def test_missing_endpoint(self):
        """Test that missing endpoint raises ValueError."""
        config = {"token": "secret"}
        with self.assertRaises(ValueError) as context:
            GtfsRtAdapter(config)
        self.assertIn("endpoint", str(context.exception))
    
    def test_invalid_endpoint_type(self):
        """Test that non-string endpoint raises ValueError."""
        config = {"endpoint": 123}
        with self.assertRaises(ValueError) as context:
            GtfsRtAdapter(config)
        self.assertIn("string", str(context.exception))
    
    def test_invalid_token_type(self):
        """Test that non-string token raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/gtfs-rt",
            "token": 12345
        }
        with self.assertRaises(ValueError) as context:
            GtfsRtAdapter(config)
        self.assertIn("token", str(context.exception))
        self.assertIn("string", str(context.exception))
    
    def test_map_cause(self):
        """Test GTFS-RT cause mapping."""
        adapter = GtfsRtAdapter({"endpoint": "https://test.com"})
        
        self.assertEqual(adapter._map_cause(1), "UNKNOWN_CAUSE")
        self.assertEqual(adapter._map_cause(2), "OTHER_CAUSE")
        self.assertEqual(adapter._map_cause(3), "TECHNICAL_PROBLEM")
        self.assertEqual(adapter._map_cause(4), "STRIKE")
        self.assertEqual(adapter._map_cause(9), "MAINTENANCE")
        self.assertEqual(adapter._map_cause(10), "CONSTRUCTION")
        self.assertEqual(adapter._map_cause(999), "UNKNOWN_CAUSE")  # Unknown value
    
    def test_map_effect(self):
        """Test GTFS-RT effect mapping."""
        adapter = GtfsRtAdapter({"endpoint": "https://test.com"})
        
        self.assertEqual(adapter._map_effect(1), "NO_SERVICE")
        self.assertEqual(adapter._map_effect(2), "REDUCED_SERVICE")
        self.assertEqual(adapter._map_effect(3), "SIGNIFICANT_DELAYS")
        self.assertEqual(adapter._map_effect(4), "DETOUR")
        self.assertEqual(adapter._map_effect(6), "MODIFIED_SERVICE")
        self.assertEqual(adapter._map_effect(999), "UNKNOWN_EFFECT")  # Unknown value
    
    def test_map_severity(self):
        """Test GTFS-RT severity level mapping."""
        adapter = GtfsRtAdapter({"endpoint": "https://test.com"})
        
        self.assertEqual(adapter._map_severity(1), "UNKNOWN_SEVERITY")
        self.assertEqual(adapter._map_severity(2), "INFO")
        self.assertEqual(adapter._map_severity(3), "WARNING")
        self.assertEqual(adapter._map_severity(4), "SEVERE")
        self.assertEqual(adapter._map_severity(999), "UNKNOWN_SEVERITY")  # Unknown value
    
    def test_config_schema(self):
        """Test that config schema is properly defined."""
        schema = GtfsRtAdapter.get_config_schema()
        
        # Should have endpoint and token fields
        field_names = [field["name"] for field in schema]
        self.assertIn("endpoint", field_names)
        self.assertIn("token", field_names)
        
        # Endpoint should be required
        endpoint_field = next(f for f in schema if f["name"] == "endpoint")
        self.assertTrue(endpoint_field["required"])
        
        # Token should be optional
        token_field = next(f for f in schema if f["name"] == "token")
        self.assertFalse(token_field["required"])


class TestGtfsRtAdapterAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for GtfsRtAdapter feed fetching."""
    
    async def test_fetch_alerts_success(self):
        """Test successful alert fetching and parsing."""
        from tests.helpers import MockResponse, create_gtfs_protobuf_bytes
        
        config = {"endpoint": "https://api.example.com/gtfs-rt"}
        adapter = GtfsRtAdapter(config)
        
        # Create mock protobuf data
        protobuf_data = create_gtfs_protobuf_bytes()
        
        # Mock httpx client
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                content=protobuf_data,
                status_code=200,
                url="https://api.example.com/gtfs-rt"
            )
            mock_client.get.return_value = mock_response
            
            # Fetch alerts
            alerts = await adapter.fetch_alerts()
            
            # Verify
            self.assertEqual(len(alerts), 1)
            alert = alerts[0]
            
            self.assertEqual(alert["cause"], "CONSTRUCTION")
            self.assertEqual(alert["effect"], "DETOUR")
            self.assertEqual(alert["severity_level"], "WARNING")
            self.assertTrue(alert["is_active"])
            
            # Check translations
            self.assertEqual(len(alert["translations"]), 1)
            self.assertEqual(alert["translations"][0]["language"], "en")
            self.assertEqual(alert["translations"][0]["header_text"], "Construction Alert")
            
            # Check active periods
            self.assertEqual(len(alert["active_periods"]), 1)
            
            # Check informed entities
            self.assertEqual(len(alert["informed_entities"]), 1)
            self.assertEqual(alert["informed_entities"][0]["route_id"], "route-1")
    
    async def test_fetch_alerts_with_token(self):
        """Test that authentication token is properly sent."""
        from tests.helpers import MockResponse, create_gtfs_protobuf_bytes
        
        config = {
            "endpoint": "https://api.example.com/gtfs-rt",
            "token": "secret-token"
        }
        adapter = GtfsRtAdapter(config)
        
        protobuf_data = create_gtfs_protobuf_bytes()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                content=protobuf_data,
                status_code=200,
                url="https://api.example.com/gtfs-rt"
            )
            mock_client.get.return_value = mock_response
            
            await adapter.fetch_alerts()
            
            # Verify Authorization header was sent
            call_args = mock_client.get.call_args
            headers = call_args[1].get("headers", {})
            self.assertEqual(headers.get("Authorization"), "Bearer secret-token")
    
    async def test_fetch_alerts_http_error(self):
        """Test handling of HTTP errors."""
        config = {"endpoint": "https://api.example.com/gtfs-rt"}
        adapter = GtfsRtAdapter(config)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Simulate HTTP error
            import httpx
            mock_client.get.side_effect = httpx.HTTPError("Connection failed")
            
            with self.assertRaises(ValueError) as context:
                await adapter.fetch_alerts()
            
            self.assertIn("Failed to fetch GTFS-RT feed", str(context.exception))
    
    async def test_fetch_alerts_invalid_protobuf(self):
        """Test handling of invalid protobuf data."""
        from tests.helpers import MockResponse
        
        config = {"endpoint": "https://api.example.com/gtfs-rt"}
        adapter = GtfsRtAdapter(config)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Return invalid protobuf data
            mock_response = MockResponse(
                content=b"invalid protobuf data",
                status_code=200,
                url="https://api.example.com/gtfs-rt"
            )
            mock_client.get.return_value = mock_response
            
            with self.assertRaises(ValueError) as context:
                await adapter.fetch_alerts()
            
            self.assertIn("Failed to parse GTFS-RT protobuf", str(context.exception))
    
    async def test_filter_expired_alerts(self):
        """Test that expired alerts are filtered out."""
        from tests.helpers import MockResponse
        
        config = {"endpoint": "https://api.example.com/gtfs-rt"}
        adapter = GtfsRtAdapter(config)
        
        # Create feed with expired alert
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = int(time.time())
        
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "expired-alert"
        
        alert = entity.alert
        alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
        alert.effect = gtfs_realtime_pb2.Alert.DETOUR
        
        header_translation = gtfs_realtime_pb2.TranslatedString.Translation()
        header_translation.text = "Old Alert"
        header_translation.language = "en"
        alert.header_text.translation.append(header_translation)
        
        # Set end time in the past
        period = gtfs_realtime_pb2.TimeRange()
        period.start = int(time.time()) - 7200  # 2 hours ago
        period.end = int(time.time()) - 3600    # 1 hour ago
        alert.active_period.append(period)
        
        feed.entity.append(entity)
        protobuf_data = feed.SerializeToString()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                content=protobuf_data,
                status_code=200,
                url="https://api.example.com/gtfs-rt"
            )
            mock_client.get.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Should be filtered out
            self.assertEqual(len(alerts), 0)
    
    async def test_filter_future_alerts(self):
        """Test that alerts starting more than 1 month in future are filtered."""
        from tests.helpers import MockResponse
        
        config = {"endpoint": "https://api.example.com/gtfs-rt"}
        adapter = GtfsRtAdapter(config)
        
        # Create feed with far-future alert
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = int(time.time())
        
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "future-alert"
        
        alert = entity.alert
        alert.cause = gtfs_realtime_pb2.Alert.MAINTENANCE
        alert.effect = gtfs_realtime_pb2.Alert.NO_SERVICE
        
        header_translation = gtfs_realtime_pb2.TranslatedString.Translation()
        header_translation.text = "Future Alert"
        header_translation.language = "en"
        alert.header_text.translation.append(header_translation)
        
        # Set start time more than 1 month in the future
        period = gtfs_realtime_pb2.TimeRange()
        period.start = int(time.time()) + (31 * 24 * 60 * 60)  # 31 days from now
        period.end = int(time.time()) + (32 * 24 * 60 * 60)
        alert.active_period.append(period)
        
        feed.entity.append(entity)
        protobuf_data = feed.SerializeToString()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                content=protobuf_data,
                status_code=200,
                url="https://api.example.com/gtfs-rt"
            )
            mock_client.get.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Should be filtered out
            self.assertEqual(len(alerts), 0)
    
    async def test_default_translation_when_missing(self):
        """Test that default translation is created when none provided."""
        from tests.helpers import MockResponse
        
        config = {"endpoint": "https://api.example.com/gtfs-rt"}
        adapter = GtfsRtAdapter(config)
        
        # Create feed without translations
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = int(time.time())
        
        entity = gtfs_realtime_pb2.FeedEntity()
        entity.id = "no-translation-alert"
        
        alert = entity.alert
        alert.cause = gtfs_realtime_pb2.Alert.OTHER_CAUSE
        # No header_text or description
        
        period = gtfs_realtime_pb2.TimeRange()
        period.start = int(time.time())
        period.end = int(time.time()) + 3600
        alert.active_period.append(period)
        
        feed.entity.append(entity)
        protobuf_data = feed.SerializeToString()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                content=protobuf_data,
                status_code=200,
                url="https://api.example.com/gtfs-rt"
            )
            mock_client.get.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Should have default translation
            self.assertEqual(len(alerts), 1)
            self.assertEqual(len(alerts[0]["translations"]), 1)
            self.assertEqual(alerts[0]["translations"][0]["language"], "de-DE")
            self.assertEqual(alerts[0]["translations"][0]["header_text"], "Service Alert")


if __name__ == '__main__':
    unittest.main()
