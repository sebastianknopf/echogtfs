"""
Unit tests for SiriLiteAdapter.

Tests SIRI-Lite XML feed parsing and alert transformation for Swiss dialect.
"""

import time
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, patch

# Setup test environment before importing echogtfs
from tests.test_config import setup_test_environment
setup_test_environment()

from echogtfs.models import SiriLiteDialect
from echogtfs.services.adapters.sirilite import SiriLiteAdapter


class TestSiriLiteAdapter(unittest.TestCase):
    """Test SiriLiteAdapter configuration and helper methods."""
    
    def test_valid_config_swiss(self):
        """Test adapter initialization with valid Swiss config."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss",
            "token": "secret"
        }
        adapter = SiriLiteAdapter(config)
        self.assertEqual(adapter.config["endpoint"], "https://api.example.com/siri-lite")
        self.assertEqual(adapter.config["dialect"], "swiss")
    
    def test_valid_config_without_token(self):
        """Test adapter initialization without token (optional)."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        self.assertNotIn("token", adapter.config)
    
    def test_missing_endpoint(self):
        """Test that missing endpoint raises ValueError."""
        config = {"dialect": "swiss"}
        with self.assertRaises(ValueError) as context:
            SiriLiteAdapter(config)
        self.assertIn("endpoint", str(context.exception))
    
    def test_missing_dialect(self):
        """Test that missing dialect raises ValueError."""
        config = {"endpoint": "https://api.example.com/siri-lite"}
        with self.assertRaises(ValueError) as context:
            SiriLiteAdapter(config)
        self.assertIn("dialect", str(context.exception))
    
    def test_invalid_dialect(self):
        """Test that invalid dialect raises ValueError."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "invalid_dialect"
        }
        with self.assertRaises(ValueError) as context:
            SiriLiteAdapter(config)
        self.assertIn("swiss", str(context.exception).lower())
    
    def test_config_with_filter(self):
        """Test adapter initialization with participant filter."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss",
            "filter": "PARTICIPANT_1,PARTICIPANT_2"
        }
        adapter = SiriLiteAdapter(config)
        self.assertEqual(adapter.config["filter"], "PARTICIPANT_1,PARTICIPANT_2")
    
    def test_extract_situation_elements(self):
        """Test extraction of PtSituationElements from XML."""
        from tests.helpers import create_siri_lite_xml
        
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        xml_content = create_siri_lite_xml()
        root = ET.fromstring(xml_content)
        
        situations, producer_ref = adapter._extract_situation_elements(root)
        
        self.assertEqual(len(situations), 1)
        self.assertEqual(producer_ref, "TEST_PRODUCER")
    
    def test_is_in_publication_window_valid(self):
        """Test situation within publication window."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        # Create a situation element with current publication window
        xml = f"""
        <PtSituationElement xmlns="http://www.siri.org.uk/siri">
            <PublicationWindow>
                <StartTime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 3600))}</StartTime>
                <EndTime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 3600))}</EndTime>
            </PublicationWindow>
        </PtSituationElement>
        """
        situation = ET.fromstring(xml)
        
        current_timestamp = int(time.time())
        result = adapter._is_in_publication_window(situation, current_timestamp)
        
        self.assertTrue(result)
    
    def test_is_in_publication_window_expired(self):
        """Test situation outside publication window (expired)."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        # Create a situation element with past publication window
        xml = f"""
        <PtSituationElement xmlns="http://www.siri.org.uk/siri">
            <PublicationWindow>
                <StartTime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 7200))}</StartTime>
                <EndTime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 3600))}</EndTime>
            </PublicationWindow>
        </PtSituationElement>
        """
        situation = ET.fromstring(xml)
        
        current_timestamp = int(time.time())
        result = adapter._is_in_publication_window(situation, current_timestamp)
        
        self.assertFalse(result)
    
    def test_is_in_publication_window_too_far_future(self):
        """Test situation starting more than 30 days in future is filtered."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        # Create a situation element starting 31 days in future
        future_start = time.time() + (31 * 24 * 60 * 60)
        xml = f"""
        <PtSituationElement xmlns="http://www.siri.org.uk/siri">
            <PublicationWindow>
                <StartTime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(future_start))}</StartTime>
                <EndTime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(future_start + 3600))}</EndTime>
            </PublicationWindow>
        </PtSituationElement>
        """
        situation = ET.fromstring(xml)
        
        current_timestamp = int(time.time())
        result = adapter._is_in_publication_window(situation, current_timestamp)
        
        self.assertFalse(result)
    
    def test_matches_participant_filter_with_match(self):
        """Test participant filter matching."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss",
            "filter": "PARTICIPANT_A, PARTICIPANT_B"
        }
        adapter = SiriLiteAdapter(config)
        
        xml = """
        <PtSituationElement xmlns="http://www.siri.org.uk/siri">
            <SituationNumber>SIT-123</SituationNumber>
            <ParticipantRef>PARTICIPANT_A</ParticipantRef>
        </PtSituationElement>
        """
        situation = ET.fromstring(xml)
        
        result = adapter._matches_participant_filter(situation)
        self.assertTrue(result)
    
    def test_matches_participant_filter_without_match(self):
        """Test participant filter not matching."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss",
            "filter": "PARTICIPANT_A, PARTICIPANT_B"
        }
        adapter = SiriLiteAdapter(config)
        
        xml = """
        <PtSituationElement xmlns="http://www.siri.org.uk/siri">
            <SituationNumber>SIT-123</SituationNumber>
            <ParticipantRef>PARTICIPANT_C</ParticipantRef>
        </PtSituationElement>
        """
        situation = ET.fromstring(xml)
        
        result = adapter._matches_participant_filter(situation)
        self.assertFalse(result)
    
    def test_matches_participant_filter_no_filter(self):
        """Test that all situations pass when no filter is set."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        xml = """
        <PtSituationElement xmlns="http://www.siri.org.uk/siri">
            <SituationNumber>SIT-123</SituationNumber>
            <ParticipantRef>ANY_PARTICIPANT</ParticipantRef>
        </PtSituationElement>
        """
        situation = ET.fromstring(xml)
        
        result = adapter._matches_participant_filter(situation)
        self.assertTrue(result)
    
    def test_config_schema(self):
        """Test that config schema is properly defined."""
        schema = SiriLiteAdapter.get_config_schema()
        
        field_names = [field["name"] for field in schema]
        self.assertIn("endpoint", field_names)
        self.assertIn("dialect", field_names)
        self.assertIn("token", field_names)
        self.assertIn("filter", field_names)
        
        # Endpoint and dialect should be required
        endpoint_field = next(f for f in schema if f["name"] == "endpoint")
        self.assertTrue(endpoint_field["required"])
        
        dialect_field = next(f for f in schema if f["name"] == "dialect")
        self.assertTrue(dialect_field["required"])
        
        # Token and filter should be optional
        token_field = next(f for f in schema if f["name"] == "token")
        self.assertFalse(token_field["required"])
        
        filter_field = next(f for f in schema if f["name"] == "filter")
        self.assertFalse(filter_field["required"])


class TestSiriLiteAdapterAsync(unittest.IsolatedAsyncioTestCase):
    """Async tests for SiriLiteAdapter feed fetching."""
    
    async def test_fetch_alerts_swiss_success(self):
        """Test successful alert fetching with Swiss dialect."""
        from tests.helpers import MockResponse, create_siri_lite_xml
        
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        xml_content = create_siri_lite_xml()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text=xml_content,
                status_code=200,
                url="https://api.example.com/siri-lite"
            )
            mock_client.get.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Verify at least one alert was parsed
            self.assertGreater(len(alerts), 0)
            
            # Check alert structure
            alert = alerts[0]
            self.assertIn("id", alert)
            self.assertIn("translations", alert)
            self.assertIn("active_periods", alert)
    
    async def test_fetch_alerts_with_token(self):
        """Test that authentication token is properly sent."""
        from tests.helpers import MockResponse, create_siri_lite_xml
        
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss",
            "token": "secret-token"
        }
        adapter = SiriLiteAdapter(config)
        
        xml_content = create_siri_lite_xml()
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text=xml_content,
                status_code=200,
                url="https://api.example.com/siri-lite"
            )
            mock_client.get.return_value = mock_response
            
            await adapter.fetch_alerts()
            
            # Verify Authorization header was sent
            call_args = mock_client.get.call_args
            headers = call_args[1].get("headers", {})
            self.assertEqual(headers.get("Authorization"), "Bearer secret-token")
    
    async def test_fetch_alerts_http_error(self):
        """Test handling of HTTP errors."""
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            import httpx
            mock_client.get.side_effect = httpx.HTTPError("Connection failed")
            
            with self.assertRaises(ValueError) as context:
                await adapter.fetch_alerts()
            
            self.assertIn("Failed to fetch SIRI-Lite feed", str(context.exception))
    
    async def test_fetch_alerts_invalid_xml(self):
        """Test handling of invalid XML data."""
        from tests.helpers import MockResponse
        
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            mock_response = MockResponse(
                text="<invalid>xml",
                status_code=200,
                url="https://api.example.com/siri-lite"
            )
            mock_client.get.return_value = mock_response
            
            with self.assertRaises(ValueError) as context:
                await adapter.fetch_alerts()
            
            self.assertIn("Failed to parse SIRI-Lite XML", str(context.exception))
    
    async def test_fetch_alerts_empty_feed(self):
        """Test handling of feed with no situations."""
        from tests.helpers import MockResponse
        
        config = {
            "endpoint": "https://api.example.com/siri-lite",
            "dialect": "swiss"
        }
        adapter = SiriLiteAdapter(config)
        
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
                url="https://api.example.com/siri-lite"
            )
            mock_client.get.return_value = mock_response
            
            alerts = await adapter.fetch_alerts()
            
            # Should return empty list
            self.assertEqual(len(alerts), 0)


if __name__ == '__main__':
    unittest.main()
