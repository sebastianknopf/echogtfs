import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.transformers.siriet_trip_updates_transformer import (
    SiriEtTripUpdatesTransformer,
)


class TestSiriEtTripUpdatesTransformer(unittest.TestCase):
    def setUp(self) -> None:
        self.transformer = SiriEtTripUpdatesTransformer()

    def test_scheduled_trip_can_be_kept_when_stop_sequence_is_incomplete(self) -> None:
        payload = self._build_payload(extra_journey="false", complete_sequence="false")
        trips = self.transformer.transform({"root": payload})

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["schedule_relationship"], "SCHEDULED")

    def test_new_trip_is_discarded_when_stop_sequence_is_incomplete(self) -> None:
        payload = self._build_payload(extra_journey="true", complete_sequence="false")

        with patch(
            "echogtfs.datasources.transformers.siriet_trip_updates_transformer.logger.warning"
        ):
            trips = self.transformer.transform({"root": payload})

        self.assertEqual(trips, [])

    def test_new_trip_is_kept_when_stop_sequence_is_complete(self) -> None:
        payload = self._build_payload(extra_journey="true", complete_sequence="true")

        trips = self.transformer.transform({"root": payload})

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["schedule_relationship"], "NEW")
        self.assertTrue(trips[0]["is_complete_stop_sequence"])

    def test_canceled_trip_is_marked_as_canceled(self) -> None:
        payload = self._build_payload(extra_journey="false", complete_sequence="false", cancellation="true")

        trips = self.transformer.transform({"root": payload})

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["schedule_relationship"], "CANCELED")

    def _build_payload(
        self,
        *,
        extra_journey: str,
        complete_sequence: str,
        cancellation: str | None = None,
    ) -> ET.Element:
        departure_time = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )
        xml = f"""<siri:Root xmlns:siri=\"http://www.siri.org.uk/siri\">
  <siri:EstimatedVehicleJourney>
    <siri:Monitored>true</siri:Monitored>
    <siri:ExtraJourney>{extra_journey}</siri:ExtraJourney>
    <siri:IsCompleteStopSequence>{complete_sequence}</siri:IsCompleteStopSequence>
    <siri:LineRef>LINE1</siri:LineRef>
    <siri:FramedVehicleJourneyRef>
      <siri:DatedVehicleJourneyRef>TRIP1</siri:DatedVehicleJourneyRef>
      <siri:DataFrameRef>2026-08-08</siri:DataFrameRef>
    </siri:FramedVehicleJourneyRef>
    <siri:RecordedCalls>
      <siri:RecordedCall>
        <siri:StopPointRef>STOP1</siri:StopPointRef>
        <siri:AimedDepartureTime>{departure_time}</siri:AimedDepartureTime>
        <siri:Order>1</siri:Order>
      </siri:RecordedCall>
    </siri:RecordedCalls>
    {f'<siri:Cancellation>{cancellation}</siri:Cancellation>' if cancellation is not None else ''}
  </siri:EstimatedVehicleJourney>
</siri:Root>"""
        return ET.fromstring(xml)


if __name__ == "__main__":
    unittest.main()
