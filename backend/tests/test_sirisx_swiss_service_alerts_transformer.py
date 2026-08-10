from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.transformers.sirisx_swiss_service_alerts_transformer import (
    SiriSxSwissServiceAlertsTransformer,
)


class TestSiriSxSwissServiceAlertsTransformer(unittest.TestCase):
    def test_transform_reads_swiss_situation(self):
        xml_payload = """
        <Siri xmlns=\"http://www.siri.org.uk/siri\">
          <PtSituationElement>
            <SituationNumber>SN-1</SituationNumber>
            <ParticipantRef>P1</ParticipantRef>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <ValidityPeriod>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </ValidityPeriod>
            <PublishingActions>
              <PublishingAction>
                <PassengerInformationAction>
                  <Perspective>general</Perspective>
                  <TextualContent>
                    <TextualContentSize>L</TextualContentSize>
                    <SummaryContent>
                      <SummaryText xml:lang=\"de\">Warnung</SummaryText>
                    </SummaryContent>
                    <DescriptionContent>
                      <DescriptionText xml:lang=\"de\">Baustelle</DescriptionText>
                    </DescriptionContent>
                  </TextualContent>
                </PassengerInformationAction>
              </PublishingAction>
            </PublishingActions>
            <Affects>
              <AffectedNetwork>
                <AffectedLine>
                  <OperatorRef>op</OperatorRef>
                  <LineRef>R1</LineRef>
                </AffectedLine>
              </AffectedNetwork>
            </Affects>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxSwissServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P1",
        )

        records = transformer.transform({"root": root, "source_name": "sirisx-swiss"})

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["id"], "sirisx-swiss-SN-1")
        self.assertEqual(records[0]["translations"][0]["header_text"], "Warnung")
        self.assertEqual(records[0]["informed_entities"][0]["route_id"], "R1")

    def test_transform_returns_empty_when_no_situations(self):
        root = ET.fromstring("<Siri xmlns=\"http://www.siri.org.uk/siri\"></Siri>")
        transformer = SiriSxSwissServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P1",
        )

        records = transformer.transform({"root": root, "source_name": "sirisx-swiss"})
        self.assertEqual(records, [])

    def test_transform_allows_participant_filter_wildcard(self):
        xml_payload = """
        <Siri xmlns="http://www.siri.org.uk/siri">
          <PtSituationElement>
            <SituationNumber>SN-1</SituationNumber>
            <ParticipantRef>P1-ABC</ParticipantRef>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <PublishingActions>
              <PublishingAction>
                <PassengerInformationAction>
                  <Perspective>general</Perspective>
                  <TextualContent>
                    <SummaryContent>
                      <SummaryText xml:lang="de">Warnung</SummaryText>
                    </SummaryContent>
                  </TextualContent>
                </PassengerInformationAction>
              </PublishingAction>
            </PublishingActions>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxSwissServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P1-*",
        )

        records = transformer.transform({"root": root, "source_name": "sirisx-swiss"})
        self.assertEqual(len(records), 1)

    def test_transform_rejects_non_matching_participant_filter_wildcard(self):
        xml_payload = """
        <Siri xmlns="http://www.siri.org.uk/siri">
          <PtSituationElement>
            <SituationNumber>SN-1</SituationNumber>
            <ParticipantRef>X1-ABC</ParticipantRef>
            <PublicationWindow>
              <StartTime>2026-01-01T00:00:00Z</StartTime>
              <EndTime>2099-01-01T00:00:00Z</EndTime>
            </PublicationWindow>
            <PublishingActions>
              <PublishingAction>
                <PassengerInformationAction>
                  <Perspective>general</Perspective>
                  <TextualContent>
                    <SummaryContent>
                      <SummaryText xml:lang="de">Warnung</SummaryText>
                    </SummaryContent>
                  </TextualContent>
                </PassengerInformationAction>
              </PublishingAction>
            </PublishingActions>
          </PtSituationElement>
        </Siri>
        """
        root = ET.fromstring(xml_payload)
        transformer = SiriSxSwissServiceAlertsTransformer(
            make_unique_id=lambda original, source: f"{source}-{original}",
            filter_value="P1-*",
        )

        records = transformer.transform({"root": root, "source_name": "sirisx-swiss"})
        self.assertEqual(records, [])