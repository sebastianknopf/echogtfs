from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.transformers.sirisx_service_alerts_transformer import (
    SiriSxServiceAlertsTransformer,
)
from echogtfs.enum.gtfsrt import PeriodType


class TestSiriSxServiceAlertsTransformer(unittest.TestCase):
    def test_transform_reads_sirisx_situation(self):
        xml_payload = """
        <Siri xmlns=\"http://www.siri.org.uk/siri\">
          <PtSituationElement>
            <SituationNumber>42</SituationNumber>
            <ParticipantRef>P2</ParticipantRef>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <Summary xml:lang=\"en\">Line disruption</Summary>
            <Description xml:lang=\"en\">Stop skipped</Description>
            <Affects>
              <AffectedStopPoint>
                <StopPointRef>STOP-1</StopPointRef>
              </AffectedStopPoint>
            </Affects>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P2",
        )

        records = transformer.transform({"root": root, "source_name": "sx"})

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "sx-42")
        self.assertEqual(records[0]["translations"][0]["language"], "en")
        self.assertEqual(records[0]["informed_entities"][0]["stop_id"], "STOP-1")

    def test_transform_returns_empty_when_no_situations(self):
        root = ET.fromstring("<Siri xmlns=\"http://www.siri.org.uk/siri\"></Siri>")
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P2",
        )

        records = transformer.transform({"root": root, "source_name": "sx"})
        self.assertEqual(records, [])

    def test_transform_allows_participant_filter_wildcard(self):
        xml_payload = """
        <Siri xmlns="http://www.siri.org.uk/siri">
          <PtSituationElement>
            <SituationNumber>42</SituationNumber>
            <ParticipantRef>P2-ABC</ParticipantRef>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <Summary xml:lang="en">Line disruption</Summary>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="operator/P2-*",
        )

        records = transformer.transform({"root": root, "source_name": "sx"})
        self.assertEqual(len(records), 1)

    def test_transform_rejects_non_matching_participant_filter_wildcard(self):
        xml_payload = """
        <Siri xmlns="http://www.siri.org.uk/siri">
          <PtSituationElement>
            <SituationNumber>42</SituationNumber>
            <ParticipantRef>X2-ABC</ParticipantRef>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <Summary xml:lang="en">Line disruption</Summary>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="operator/P2-*",
        )

        records = transformer.transform({"root": root, "source_name": "sx"})
        self.assertEqual(records, [])

    def test_legacy_participant_filter_supports_wildcard(self):
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P2-*",
        )
        situation = ET.fromstring(
            """
            <PtSituationElement xmlns="http://www.siri.org.uk/siri">
              <ParticipantRef>P2-ABC</ParticipantRef>
            </PtSituationElement>
            """
        )

        self.assertTrue(transformer._matches_participant_filter(situation))

    def test_legacy_participant_filter_rejects_non_matching_wildcard(self):
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P2-*",
        )
        situation = ET.fromstring(
            """
            <PtSituationElement xmlns="http://www.siri.org.uk/siri">
              <ParticipantRef>X2-ABC</ParticipantRef>
            </PtSituationElement>
            """
        )

        self.assertFalse(transformer._matches_participant_filter(situation))

    def test_transform_skips_closed_progress(self):
        xml_payload = """
        <Siri xmlns="http://www.siri.org.uk/siri">
          <PtSituationElement>
            <SituationNumber>42</SituationNumber>
            <ParticipantRef>P2</ParticipantRef>
            <Progress>closed</Progress>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <Summary xml:lang="en">Line disruption</Summary>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P2",
        )

        records = transformer.transform({"root": root, "source_name": "sx"})
        self.assertEqual(records, [])

    def test_transform_marks_closing_progress(self):
        xml_payload = """
        <Siri xmlns="http://www.siri.org.uk/siri">
          <PtSituationElement>
            <SituationNumber>42</SituationNumber>
            <ParticipantRef>P2</ParticipantRef>
            <Progress>closing</Progress>
            <ValidityPeriod>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2026-01-02T00:00:00Z</EndTime>
            </ValidityPeriod>
            <ValidityPeriod>
              <StartTime>2026-01-03T00:00:00Z</StartTime>
              <EndTime>2026-01-04T00:00:00Z</EndTime>
            </ValidityPeriod>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2026-01-02T00:00:00Z</EndTime>
            </PublicationWindow>
            <PublicationWindow>
              <StartTime>2026-01-03T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <Summary xml:lang="en">Line disruption</Summary>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P2",
        )

        records = transformer.transform({"root": root, "source_name": "sx"})

        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["is_closing_alert"])
        self.assertEqual(records[0]["effect"], "UNKNOWN_EFFECT")
        self.assertEqual(len(records[0]["active_periods"]), 2)

        impact_period = records[0]["active_periods"][0]
        communication_period = records[0]["active_periods"][1]

        self.assertEqual(impact_period["period_type"], PeriodType.IMPACT_PERIOD)
        self.assertEqual(impact_period["start_time"], 1767398400)
        self.assertIsNone(impact_period["end_time"])

        self.assertEqual(communication_period["period_type"], PeriodType.COMMUNICATION_PERIOD)
        self.assertEqual(communication_period["start_time"], 1767398400)
        self.assertIsNone(communication_period["end_time"])