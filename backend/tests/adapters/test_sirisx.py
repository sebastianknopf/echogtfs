"""
Unit tests for SiriSxAdapter.

Tests SIRI-SX XML feed parsing with request/response method.
"""

import time
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

# Setup test environment before importing echogtfs
from tests.test_config import setup_test_environment
setup_test_environment()

from echogtfs.models import SiriSxDialect, SiriSxMethod
from echogtfs.services.adapters.sirisx import SiriSxAdapter


class TestSiriSxAdapter(unittest.TestCase):
    """Test SiriSxAdapter configuration and helper methods."""
    
    def test_valid_config(self):
        """Test adapter initialization with valid config."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        self.assertEqual(adapter.config["endpoint"], "https://api.example.com/siri-sx")
        self.assertEqual(adapter.config["participantref"], "MY_PARTICIPANT")
        self.assertEqual(adapter.config["method"], "request/response")
        self.assertEqual(adapter.config["dialect"], "sirisx")
    
    def test_missing_endpoint(self):
        """Test that missing endpoint raises ValueError."""
        config = {
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        with self.assertRaises(ValueError) as context:
            SiriSxAdapter(config)
        self.assertIn("endpoint", str(context.exception))
    
    def test_missing_participantref(self):
        """Test that missing participantref raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "method": "request/response",
            "dialect": "sirisx"
        }
        with self.assertRaises(ValueError) as context:
            SiriSxAdapter(config)
        self.assertIn("participantref", str(context.exception))
    
    def test_missing_method(self):
        """Test that missing method raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "dialect": "sirisx"
        }
        with self.assertRaises(ValueError) as context:
            SiriSxAdapter(config)
        self.assertIn("method", str(context.exception))
    
    def test_missing_dialect(self):
        """Test that missing dialect raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response"
        }
        with self.assertRaises(ValueError) as context:
            SiriSxAdapter(config)
        self.assertIn("dialect", str(context.exception))
    
    def test_invalid_method(self):
        """Test that invalid method raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "invalid_method",
            "dialect": "sirisx"
        }
        with self.assertRaises(ValueError) as context:
            SiriSxAdapter(config)
        self.assertIn("Invalid method", str(context.exception))
    
    def test_invalid_dialect(self):
        """Test that invalid dialect raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "invalid_dialect"
        }
        with self.assertRaises(ValueError) as context:
            SiriSxAdapter(config)
        self.assertIn("Invalid dialect", str(context.exception))
    
    def test_config_with_filter(self):
        """Test adapter initialization with filter."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx",
            "filter": "PARTICIPANT_1,PARTICIPANT_2"
        }
        adapter = SiriSxAdapter(config)
        self.assertEqual(adapter.config["filter"], "PARTICIPANT_1,PARTICIPANT_2")
    
    def test_resolve_placeholders(self):
        """Test placeholder replacement in endpoint URL."""
        config = {
            "endpoint": "https://api.example.com/siri-sx/{participantRef}/data",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        resolved = adapter._resolve_placeholders(config["endpoint"])
        self.assertEqual(resolved, "https://api.example.com/siri-sx/MY_PARTICIPANT/data")
    
    def test_resolve_placeholders_case_insensitive(self):
        """Test that placeholder replacement is case-insensitive."""
        config = {
            "endpoint": "https://api.example.com/{PARTICIPANTREF}/data",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        resolved = adapter._resolve_placeholders(config["endpoint"])
        self.assertEqual(resolved, "https://api.example.com/MY_PARTICIPANT/data")
    
    def test_build_request_xml(self):
        """Test SIRI-SX request XML generation."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        xml_string = adapter._build_request_xml()
        
        # Verify it's valid XML
        root = ET.fromstring(xml_string)
        
        # Verify structure
        self.assertEqual(root.tag, "{http://www.siri.org.uk/siri}Siri")
        
        # Find RequestorRef
        SIRI_NS = {'siri': 'http://www.siri.org.uk/siri'}
        requestor_ref = root.find('.//siri:RequestorRef', SIRI_NS)
        self.assertIsNotNone(requestor_ref)
        self.assertEqual(requestor_ref.text, "MY_PARTICIPANT")
        
        # Verify SituationExchangeRequest exists
        sx_request = root.find('.//siri:SituationExchangeRequest', SIRI_NS)
        self.assertIsNotNone(sx_request)
    
    def test_config_schema(self):
        """Test that config schema is properly defined."""
        schema = SiriSxAdapter.get_config_schema()
        
        field_names = [field["name"] for field in schema]
        self.assertIn("endpoint", field_names)
        self.assertIn("participantref", field_names)
        self.assertIn("method", field_names)
        self.assertIn("dialect", field_names)
        self.assertIn("filter", field_names)
        
        # Required fields
        endpoint_field = next(f for f in schema if f["name"] == "endpoint")
        self.assertTrue(endpoint_field["required"])
        
        participantref_field = next(f for f in schema if f["name"] == "participantref")
        self.assertTrue(participantref_field["required"])
        
        method_field = next(f for f in schema if f["name"] == "method")
        self.assertTrue(method_field["required"])
        
        dialect_field = next(f for f in schema if f["name"] == "dialect")
        self.assertTrue(dialect_field["required"])
        
        # Optional fields
        filter_field = next(f for f in schema if f["name"] == "filter")
        self.assertFalse(filter_field["required"])


class TestSiriSxAdapterAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for SiriSxAdapter feed fetching."""
    
    async def test_fetch_alerts_success(self):
        """Test successful alert fetching with SIRI-SX."""
        from tests.helpers import MockResponse, create_siri_sx_xml
        
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        xml_content = create_siri_sx_xml()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text=xml_content,
                status_code=200,
                url="https://api.example.com/siri-sx"
            )
            mock_client.post.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Verify at least one alert was parsed
            self.assertGreater(len(alerts), 0)
            
            # Check alert structure
            alert = alerts[0]
            self.assertIn("id", alert)
            self.assertIn("translations", alert)
            self.assertIn("active_periods", alert)
    
    async def test_fetch_alerts_uses_post_method(self):
        """Test that SIRI-SX uses POST with XML payload."""
        from tests.helpers import MockResponse, create_siri_sx_xml
        
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        xml_content = create_siri_sx_xml()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text=xml_content,
                status_code=200,
                url="https://api.example.com/siri-sx"
            )
            mock_client.post.return_value = mock_response
            
            await adapter.fetch_alerts()
            
            # Verify POST was called (not GET)
            mock_client.post.assert_called_once()
            
            # Verify Content-Type header
            call_args = mock_client.post.call_args
            headers = call_args[1].get("headers", {})
            self.assertIn("application/xml", headers.get("Content-Type", ""))
            
            # Verify XML content was sent
            xml_payload = call_args[1].get("content", "")
            self.assertIn("Siri", xml_payload)
            self.assertIn("MY_PARTICIPANT", xml_payload)
    
    async def test_fetch_alerts_publish_subscribe_not_implemented(self):
        """Test that publish/subscribe method raises NotImplementedError."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "publish/subscribe",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        with self.assertRaises(NotImplementedError) as context:
            await adapter.fetch_alerts()
        
        self.assertIn("publish/subscribe", str(context.exception))
    
    async def test_fetch_alerts_http_error(self):
        """Test handling of HTTP errors."""
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            import httpx
            mock_client.post.side_effect = httpx.HTTPError("Connection failed")
            
            with self.assertRaises(ValueError) as context:
                await adapter.fetch_alerts()
            
            self.assertIn("Failed to fetch SIRI-SX feed", str(context.exception))
    
    async def test_fetch_alerts_invalid_xml(self):
        """Test handling of invalid XML response."""
        from tests.helpers import MockResponse
        
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text="<invalid>xml",
                status_code=200,
                url="https://api.example.com/siri-sx"
            )
            mock_client.post.return_value = mock_response
            
            with self.assertRaises(ValueError) as context:
                await adapter.fetch_alerts()
            
            self.assertIn("Failed to parse SIRI-SX XML", str(context.exception))
    
    async def test_fetch_alerts_empty_feed(self):
        """Test handling of feed with no situations."""
        from tests.helpers import MockResponse
        
        config = {
            "endpoint": "https://api.example.com/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <Siri xmlns="http://www.siri.org.uk/siri" version="2.0">
            <ServiceDelivery>
                <ResponseTimestamp>2024-01-15T10:00:00Z</ResponseTimestamp>
                <ProducerRef>TEST_PRODUCER</ProducerRef>
                <SituationExchangeDelivery>
                    <Situations>
                    </Situations>
                </SituationExchangeDelivery>
            </ServiceDelivery>
        </Siri>"""
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text=xml_content,
                status_code=200,
                url="https://api.example.com/siri-sx"
            )
            mock_client.post.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Should return empty list
            self.assertEqual(len(alerts), 0)
    
    async def test_fetch_alerts_with_placeholder_in_url(self):
        """Test that URL placeholders are properly resolved."""
        from tests.helpers import MockResponse, create_siri_sx_xml
        
        config = {
            "endpoint": "https://api.example.com/{participantRef}/siri-sx",
            "participantref": "MY_PARTICIPANT",
            "method": "request/response",
            "dialect": "sirisx"
        }
        adapter = SiriSxAdapter(config)
        
        xml_content = create_siri_sx_xml()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text=xml_content,
                status_code=200,
                url="https://api.example.com/MY_PARTICIPANT/siri-sx"
            )
            mock_client.post.return_value = mock_response
            
            await adapter.fetch_alerts()
            
            # Verify the resolved URL was used
            call_args = mock_client.post.call_args
            called_url = call_args[0][0]
            self.assertEqual(called_url, "https://api.example.com/MY_PARTICIPANT/siri-sx")


if __name__ == '__main__':
    unittest.main()
