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

    def test_operator_filter_supports_wildcard(self) -> None:
        transformer = SiriEtTripUpdatesTransformer(filter_value="OP-*")
        payload = self._build_payload(
            extra_journey="false",
            complete_sequence="false",
            operator_ref="OP-ABC",
        )

        trips = transformer.transform({"root": payload})

        self.assertEqual(len(trips), 1)

    def test_operator_filter_rejects_non_matching_wildcard(self) -> None:
        transformer = SiriEtTripUpdatesTransformer(filter_value="OP-*")
        payload = self._build_payload(
            extra_journey="false",
            complete_sequence="false",
            operator_ref="AGENCY-1",
        )

        trips = transformer.transform({"root": payload})

        self.assertEqual(trips, [])

    def test_recorded_call_uses_expected_times(self) -> None:
        expected_departure_time = datetime.now(timezone.utc) + timedelta(hours=1)
        payload = self._build_payload(
            extra_journey="false",
            complete_sequence="false",
            recorded_call_times=(
                "",
                expected_departure_time.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            ),
        )

        trips = self.transformer.transform({"root": payload})

        self.assertEqual(len(trips), 1)
        stop_event = trips[0]["stop_events"][0]
        self.assertEqual(stop_event["schedule_relationship"], "SCHEDULED")
        self.assertEqual(stop_event["arrival_time"], expected_departure_time.replace(microsecond=0))
        self.assertEqual(stop_event["departure_time"], expected_departure_time.replace(microsecond=0))

    def test_scheduled_intermediate_stops_are_extracted_in_order_from_aimed_departure_times(self) -> None:
        now = datetime.now(timezone.utc)
        stop_1_time = now + timedelta(minutes=5)
        stop_2_time = now + timedelta(minutes=10)
        stop_3_time = now + timedelta(minutes=15)
        stop_4_time = now + timedelta(minutes=20)

        xml = f"""<siri:Root xmlns:siri=\"http://www.siri.org.uk/siri\">
  <siri:EstimatedVehicleJourney>
    <siri:Monitored>true</siri:Monitored>
    <siri:OperatorRef>OP1</siri:OperatorRef>
    <siri:ExtraJourney>false</siri:ExtraJourney>
    <siri:IsCompleteStopSequence>false</siri:IsCompleteStopSequence>
    <siri:LineRef>LINE1</siri:LineRef>
    <siri:FramedVehicleJourneyRef>
      <siri:DatedVehicleJourneyRef>TRIP1</siri:DatedVehicleJourneyRef>
      <siri:DataFrameRef>{now.date().isoformat()}</siri:DataFrameRef>
    </siri:FramedVehicleJourneyRef>
    <siri:RecordedCalls>
      <siri:RecordedCall>
        <siri:StopPointRef>STOP1</siri:StopPointRef>
        <siri:AimedDepartureTime>{stop_1_time.isoformat()}</siri:AimedDepartureTime>
        <siri:Order>1</siri:Order>
      </siri:RecordedCall>
      <siri:RecordedCall>
        <siri:StopPointRef>STOP2</siri:StopPointRef>
        <siri:AimedDepartureTime>{stop_2_time.isoformat()}</siri:AimedDepartureTime>
        <siri:Order>2</siri:Order>
      </siri:RecordedCall>
      <siri:RecordedCall>
        <siri:StopPointRef>STOP3</siri:StopPointRef>
        <siri:AimedArrivalTime>{stop_3_time.isoformat()}</siri:AimedArrivalTime>
        <siri:Order>3</siri:Order>
      </siri:RecordedCall>
      <siri:RecordedCall>
        <siri:StopPointRef>STOP4</siri:StopPointRef>
        <siri:AimedDepartureTime>{stop_4_time.isoformat()}</siri:AimedDepartureTime>
        <siri:Order>4</siri:Order>
      </siri:RecordedCall>
    </siri:RecordedCalls>
  </siri:EstimatedVehicleJourney>
</siri:Root>"""

        trips = self.transformer.transform({"root": ET.fromstring(xml)})

        self.assertEqual(len(trips), 1)
        self.assertEqual(
            trips[0]["scheduled_intermediate_stops"],
            [
                ("STOP2", stop_2_time),
                ("STOP3", stop_3_time),
            ],
        )

    def test_stop_event_relationship_prioritizes_skipped_and_added_over_no_data(self) -> None:
        resolve = self.transformer._resolve_stop_event_schedule_relationship

        self.assertEqual(
            resolve(is_canceled=True, is_added=True, has_realtime_data=False),
            "SKIPPED",
        )
        self.assertEqual(
            resolve(is_canceled=False, is_added=True, has_realtime_data=False),
            "ADDED",
        )
        self.assertEqual(
            resolve(is_canceled=False, is_added=False, has_realtime_data=False),
            "NO_DATA",
        )
        self.assertEqual(
            resolve(is_canceled=False, is_added=False, has_realtime_data=True),
            "SCHEDULED",
        )

    def test_recorded_call_extra_call_is_marked_as_added(self) -> None:
        payload = self._build_payload(
            extra_journey="false",
            complete_sequence="false",
            extra_call="true",
            recorded_call_times=("", ""),
        )

        trips = self.transformer.transform({"root": payload})

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["stop_events"][0]["schedule_relationship"], "ADDED")

    def _build_payload(
        self,
        *,
        extra_journey: str,
        complete_sequence: str,
        cancellation: str | None = None,
        operator_ref: str = "OP1",
        recorded_call_times: tuple[str, str] | None = None,
        extra_call: str = "false",
    ) -> ET.Element:
        departure_time = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )
        expected_arrival_time, expected_departure_time = recorded_call_times or ("", "")
        xml = f"""<siri:Root xmlns:siri=\"http://www.siri.org.uk/siri\">
  <siri:EstimatedVehicleJourney>
    <siri:Monitored>true</siri:Monitored>
        <siri:OperatorRef>{operator_ref}</siri:OperatorRef>
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
    <siri:ExtraCall>{extra_call}</siri:ExtraCall>
                {f'<siri:ExpectedArrivalTime>{expected_arrival_time}</siri:ExpectedArrivalTime>' if expected_arrival_time else ''}
                {f'<siri:ExpectedDepartureTime>{expected_departure_time}</siri:ExpectedDepartureTime>' if expected_departure_time else ''}
        <siri:Order>1</siri:Order>
      </siri:RecordedCall>
    </siri:RecordedCalls>
    {f'<siri:Cancellation>{cancellation}</siri:Cancellation>' if cancellation is not None else ''}
  </siri:EstimatedVehicleJourney>
</siri:Root>"""
        return ET.fromstring(xml)


if __name__ == "__main__":
    unittest.main()
