"""
Test helpers and utilities for echogtfs tests.

Provides common mock objects and helper functions for testing.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock


class MockAsyncSession:
    """Mock AsyncSession for database operations."""
    
    def __init__(self):
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockResponse:
    """Mock httpx Response object."""
    
    def __init__(self, content: bytes = b"", text: str = "", status_code: int = 200, url: str = ""):
        self.content = content
        self.text = text
        self.status_code = status_code
        self.url = url
    
    def raise_for_status(self):
        """Raise HTTPError if status code indicates error."""
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=MagicMock(),
                response=self
            )


def create_gtfs_protobuf_bytes() -> bytes:
    """Create a minimal valid GTFS-RT protobuf message."""
    from echogtfs import gtfs_realtime_pb2
    import time
    
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = int(time.time())
    
    # Add an alert entity
    entity = gtfs_realtime_pb2.FeedEntity()
    entity.id = "alert-1"
    
    alert = entity.alert
    alert.cause = gtfs_realtime_pb2.Alert.CONSTRUCTION
    alert.effect = gtfs_realtime_pb2.Alert.DETOUR
    alert.severity_level = gtfs_realtime_pb2.Alert.WARNING
    
    # Add header text
    header_translation = gtfs_realtime_pb2.TranslatedString.Translation()
    header_translation.text = "Construction Alert"
    header_translation.language = "en"
    alert.header_text.translation.append(header_translation)
    
    # Add description
    desc_translation = gtfs_realtime_pb2.TranslatedString.Translation()
    desc_translation.text = "Road work in progress"
    desc_translation.language = "en"
    alert.description_text.translation.append(desc_translation)
    
    # Add active period (current time + 1 hour)
    period = gtfs_realtime_pb2.TimeRange()
    period.start = int(time.time())
    period.end = int(time.time()) + 3600
    alert.active_period.append(period)
    
    # Add informed entity
    informed_entity = gtfs_realtime_pb2.EntitySelector()
    informed_entity.route_id = "route-1"
    alert.informed_entity.append(informed_entity)
    
    feed.entity.append(entity)
    
    return feed.SerializeToString()


def create_siri_lite_xml() -> str:
    """Create a minimal valid SIRI-Lite XML response (Swiss dialect)."""
    from datetime import datetime, timezone, timedelta
    
    # Current time and time windows
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=8)
    pub_start = now - timedelta(hours=2)
    pub_end = now + timedelta(hours=10)
    
    # Format as ISO strings
    start_str = start.isoformat().replace('+00:00', 'Z')
    end_str = end.isoformat().replace('+00:00', 'Z')
    pub_start_str = pub_start.isoformat().replace('+00:00', 'Z')
    pub_end_str = pub_end.isoformat().replace('+00:00', 'Z')
    response_str = now.isoformat().replace('+00:00', 'Z')
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Siri xmlns="http://www.siri.org.uk/siri" version="2.0">
    <ServiceDelivery>
        <ResponseTimestamp>{response_str}</ResponseTimestamp>
        <ProducerRef>TEST_PRODUCER</ProducerRef>
        <SituationExchangeDelivery>
            <Situations>
                <PtSituationElement>
                    <SituationNumber>SIT-123</SituationNumber>
                    <ParticipantRef>TEST_PARTICIPANT</ParticipantRef>
                    <ValidityPeriod>
                        <StartTime>{start_str}</StartTime>
                        <EndTime>{end_str}</EndTime>
                    </ValidityPeriod>
                    <PublicationWindow>
                        <StartTime>{pub_start_str}</StartTime>
                        <EndTime>{pub_end_str}</EndTime>
                    </PublicationWindow>
                    <PublishingActions>
                        <PublishingAction>
                            <PassengerInformationAction>
                                <Perspective>general</Perspective>
                                <TextualContent>
                                    <TextualContentSize>L</TextualContentSize>
                                    <SummaryContent>
                                        <SummaryText xml:lang="de">Bauarbeiten</SummaryText>
                                    </SummaryContent>
                                    <DescriptionContent>
                                        <DescriptionText xml:lang="de">Störung aufgrund von Bauarbeiten</DescriptionText>
                                    </DescriptionContent>
                                </TextualContent>
                            </PassengerInformationAction>
                        </PublishingAction>
                    </PublishingActions>
                </PtSituationElement>
            </Situations>
        </SituationExchangeDelivery>
    </ServiceDelivery>
</Siri>"""
    return xml


def create_siri_sx_xml() -> str:
    """Create a minimal valid SIRI-SX XML response."""
    from datetime import datetime, timezone, timedelta
    
    # Current time and time windows
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)
    end = now + timedelta(hours=8)
    pub_start = now - timedelta(hours=2)
    pub_end = now + timedelta(hours=10)
    
    # Format as ISO strings
    start_str = start.isoformat().replace('+00:00', 'Z')
    end_str = end.isoformat().replace('+00:00', 'Z')
    pub_start_str = pub_start.isoformat().replace('+00:00', 'Z')
    pub_end_str = pub_end.isoformat().replace('+00:00', 'Z')
    response_str = now.isoformat().replace('+00:00', 'Z')
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Siri xmlns="http://www.siri.org.uk/siri" version="2.0">
    <ServiceDelivery>
        <ResponseTimestamp>{response_str}</ResponseTimestamp>
        <ProducerRef>TEST_PRODUCER</ProducerRef>
        <SituationExchangeDelivery>
            <Situations>
                <PtSituationElement>
                    <SituationNumber>SIT-456</SituationNumber>
                    <ParticipantRef>TEST_PARTICIPANT</ParticipantRef>
                    <ValidityPeriod>
                        <StartTime>{start_str}</StartTime>
                        <EndTime>{end_str}</EndTime>
                    </ValidityPeriod>
                    <PublicationWindow>
                        <StartTime>{pub_start_str}</StartTime>
                        <EndTime>{pub_end_str}</EndTime>
                    </PublicationWindow>
                    <Summary xml:lang="de">Baustelle</Summary>
                    <Detail xml:lang="de">Bauarbeiten auf der Strecke</Detail>
                </PtSituationElement>
            </Situations>
        </SituationExchangeDelivery>
    </ServiceDelivery>
</Siri>"""
    return xml

