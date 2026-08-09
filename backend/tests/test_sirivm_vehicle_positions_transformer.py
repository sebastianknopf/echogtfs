import os
import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-bytes-long")

from echogtfs.datasources.transformers import (
    sirivm_vehicle_positions_transformer as sirivm_vehicle_positions_transformer_module,
)
from echogtfs.datasources.transformers.sirivm_vehicle_positions_transformer import (
    SiriVmVehiclePositionsTransformer,
)
from echogtfs.enum.gtfsrt import VehicleStopStatus


class TestSiriVmVehiclePositionsTransformer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._logger_error_patcher = patch.object(
            sirivm_vehicle_positions_transformer_module.logger,
            "error",
        )
        cls._logger_warning_patcher = patch.object(
            sirivm_vehicle_positions_transformer_module.logger,
            "warning",
        )
        cls._logger_info_patcher = patch.object(
            sirivm_vehicle_positions_transformer_module.logger,
            "info",
        )
        cls._logger_error_patcher.start()
        cls._logger_warning_patcher.start()
        cls._logger_info_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._logger_info_patcher.stop()
        cls._logger_warning_patcher.stop()
        cls._logger_error_patcher.stop()
        super().tearDownClass()

    def setUp(self) -> None:
        self.transformer = SiriVmVehiclePositionsTransformer()

    def test_complete_sequence_extracts_start_and_end_from_call_bounds(self) -> None:
        now = datetime.now(timezone.utc)
        first_time = self._to_second_precision(now + timedelta(minutes=10))
        middle_time = self._to_second_precision(now + timedelta(minutes=15))
        last_time = self._to_second_precision(now + timedelta(minutes=25))

        previous_calls = f"""
<siri:PreviousCalls>
  <siri:PreviousCall>
    <siri:StopPointRef>STOP_PREV</siri:StopPointRef>
    <siri:AimedArrivalTime>{self._iso(first_time)}</siri:AimedArrivalTime>
  </siri:PreviousCall>
</siri:PreviousCalls>
"""
        monitored_call = """
<siri:MonitoredCall>
  <siri:StopPointRef>STOP_MONITORED</siri:StopPointRef>
  <siri:VehicleAtStop>true</siri:VehicleAtStop>
  <siri:Order>7</siri:Order>
</siri:MonitoredCall>
"""
        onward_calls = f"""
<siri:OnwardCalls>
  <siri:OnwardCall>
    <siri:StopPointRef>STOP_ONWARD_1</siri:StopPointRef>
    <siri:AimedDepartureTime>{self._iso(middle_time)}</siri:AimedDepartureTime>
  </siri:OnwardCall>
  <siri:OnwardCall>
    <siri:StopPointRef>STOP_ONWARD_2</siri:StopPointRef>
    <siri:AimedArrivalTime>{self._iso(last_time)}</siri:AimedArrivalTime>
  </siri:OnwardCall>
</siri:OnwardCalls>
"""

        payload = self._payload(
            self._activity(
                complete_sequence=True,
                origin_ref="ORIGIN_IGNORED",
                destination_ref="DEST_IGNORED",
                monitored_call=monitored_call,
                previous_calls=previous_calls,
                onward_calls=onward_calls,
            )
        )

        result = self.transformer.transform({"root": ET.fromstring(payload)})

        self.assertEqual(len(result), 1)
        vehicle = result[0]
        trip = vehicle["trip"]
        self.assertEqual(trip["scheduled_start_stop_id"], "STOP_PREV")
        self.assertEqual(trip["scheduled_end_stop_id"], "STOP_ONWARD_2")
        self.assertEqual(trip["scheduled_start_time"], first_time)
        self.assertEqual(trip["scheduled_end_time"], last_time)
        self.assertEqual(trip["scheduled_intermediate_stops"], [])
        self.assertEqual(vehicle["current_status"], VehicleStopStatus.STOPPED_AT.value)
        self.assertEqual(vehicle["current_stop_sequence"], 7)
        self.assertEqual(vehicle["stop_id"], "STOP_MONITORED")

    def test_incomplete_sequence_uses_origin_and_destination_without_aimed_call_times(self) -> None:
        monitored_call = """
<siri:MonitoredCall>
  <siri:StopPointRef>STOP_CURRENT</siri:StopPointRef>
  <siri:VehicleAtStop>false</siri:VehicleAtStop>
  <siri:Order>3</siri:Order>
</siri:MonitoredCall>
"""
        payload = self._payload(
            self._activity(
                complete_sequence=False,
                origin_ref="ORIGIN_REF",
                destination_ref="DESTINATION_REF",
                monitored_call=monitored_call,
            )
        )

        result = self.transformer.transform({"root": ET.fromstring(payload)})

        self.assertEqual(len(result), 1)
        vehicle = result[0]
        trip = vehicle["trip"]
        self.assertEqual(trip["scheduled_start_stop_id"], "ORIGIN_REF")
        self.assertEqual(trip["scheduled_end_stop_id"], "DESTINATION_REF")
        self.assertIsNone(trip["scheduled_start_time"])
        self.assertIsNone(trip["scheduled_end_time"])
        self.assertEqual(trip["scheduled_intermediate_stops"], [])

    def test_incomplete_sequence_keeps_origin_destination_and_extracts_intermediate_calls(self) -> None:
        now = datetime.now(timezone.utc)
        call_1 = self._to_second_precision(now + timedelta(minutes=1))
        call_2 = self._to_second_precision(now + timedelta(minutes=2))
        call_3 = self._to_second_precision(now + timedelta(minutes=3))
        call_4 = self._to_second_precision(now + timedelta(minutes=4))

        monitored_call = f"""
<siri:MonitoredCall>
  <siri:StopPointRef>STOP_MONITORED</siri:StopPointRef>
  <siri:AimedArrivalTime>{self._iso(call_2)}</siri:AimedArrivalTime>
  <siri:VehicleAtStop>false</siri:VehicleAtStop>
  <siri:Order>4</siri:Order>
</siri:MonitoredCall>
"""
        previous_calls = f"""
<siri:PreviousCalls>
  <siri:PreviousCall>
    <siri:StopPointRef>STOP_PREVIOUS</siri:StopPointRef>
    <siri:AimedDepartureTime>{self._iso(call_1)}</siri:AimedDepartureTime>
  </siri:PreviousCall>
</siri:PreviousCalls>
"""
        onward_calls = f"""
<siri:OnwardCalls>
  <siri:OnwardCall>
    <siri:StopPointRef>STOP_ONWARD_1</siri:StopPointRef>
    <siri:AimedDepartureTime>{self._iso(call_3)}</siri:AimedDepartureTime>
  </siri:OnwardCall>
  <siri:OnwardCall>
    <siri:StopPointRef>STOP_ONWARD_2</siri:StopPointRef>
    <siri:AimedArrivalTime>{self._iso(call_4)}</siri:AimedArrivalTime>
  </siri:OnwardCall>
</siri:OnwardCalls>
"""

        payload = self._payload(
            self._activity(
                complete_sequence=False,
                origin_ref="ORIGIN_FIXED",
                destination_ref="DEST_FIXED",
                monitored_call=monitored_call,
                previous_calls=previous_calls,
                onward_calls=onward_calls,
            )
        )

        with patch(
            "echogtfs.datasources.transformers.sirivm_vehicle_positions_transformer.random.sample",
            side_effect=lambda seq, sample_size: list(seq)[:sample_size],
        ):
            result = self.transformer.transform({"root": ET.fromstring(payload)})

        self.assertEqual(len(result), 1)
        trip = result[0]["trip"]
        self.assertEqual(trip["scheduled_start_stop_id"], "ORIGIN_FIXED")
        self.assertEqual(trip["scheduled_end_stop_id"], "DEST_FIXED")
        self.assertEqual(
            trip["scheduled_intermediate_stops"],
            [
                ("STOP_PREVIOUS", call_1),
                ("STOP_MONITORED", call_2),
                ("STOP_ONWARD_1", call_3),
            ],
        )

    def test_complete_sequence_without_usable_call_times_is_filtered_out(self) -> None:
        monitored_call = """
<siri:MonitoredCall>
  <siri:StopPointRef>STOP_CURRENT</siri:StopPointRef>
  <siri:VehicleAtStop>false</siri:VehicleAtStop>
</siri:MonitoredCall>
"""
        payload = self._payload(
            self._activity(
                complete_sequence=True,
                origin_ref="ORIGIN_REF",
                destination_ref="DESTINATION_REF",
                monitored_call=monitored_call,
            )
        )

        result = self.transformer.transform({"root": ET.fromstring(payload)})

        self.assertEqual(result, [])

    def test_extraction_helpers_keep_call_order_and_departure_precedence(self) -> None:
        call_departure = self._to_second_precision(datetime.now(timezone.utc) + timedelta(minutes=5))
        call_arrival = self._to_second_precision(datetime.now(timezone.utc) + timedelta(minutes=6))

        monitored_journey = ET.fromstring(
            f"""
<siri:MonitoredVehicleJourney xmlns:siri=\"http://www.siri.org.uk/siri\">
  <siri:PreviousCalls>
    <siri:PreviousCall>
      <siri:StopPointRef>STOP_PREV</siri:StopPointRef>
      <siri:AimedArrivalTime>{self._iso(call_arrival)}</siri:AimedArrivalTime>
    </siri:PreviousCall>
  </siri:PreviousCalls>
  <siri:MonitoredCall>
    <siri:StopPointRef>STOP_MONITORED</siri:StopPointRef>
    <siri:AimedDepartureTime>{self._iso(call_departure)}</siri:AimedDepartureTime>
    <siri:AimedArrivalTime>{self._iso(call_arrival)}</siri:AimedArrivalTime>
  </siri:MonitoredCall>
  <siri:OnwardCalls>
    <siri:OnwardCall>
      <siri:StopPointRef>STOP_INVALID</siri:StopPointRef>
    </siri:OnwardCall>
  </siri:OnwardCalls>
</siri:MonitoredVehicleJourney>
"""
        )

        calls = self.transformer._collect_call_candidates(monitored_journey)
        extracted = self.transformer._extract_call_stop_time_tuples(calls)

        self.assertEqual(len(calls), 3)
        self.assertEqual(
            extracted,
            [
                ("STOP_PREV", call_arrival),
                ("STOP_MONITORED", call_departure),
            ],
        )

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    @staticmethod
    def _to_second_precision(value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(microsecond=0)

    def _payload(self, *activities: str) -> str:
        body = "\n".join(activities)
        return f"""<siri:Root xmlns:siri=\"http://www.siri.org.uk/siri\">{body}</siri:Root>"""

    def _activity(
        self,
        *,
        complete_sequence: bool,
        origin_ref: str,
        destination_ref: str,
        monitored_call: str,
        previous_calls: str = "",
        onward_calls: str = "",
    ) -> str:
        now = datetime.now(timezone.utc)
        valid_until = self._iso(now + timedelta(minutes=30))
        recorded_at = self._iso(now)
        complete_value = "true" if complete_sequence else "false"

        return f"""
<siri:VehicleActivity>
  <siri:ValidUntilTime>{valid_until}</siri:ValidUntilTime>
  <siri:RecordedAtTime>{recorded_at}</siri:RecordedAtTime>
  <siri:MonitoredVehicleJourney>
    <siri:Monitored>true</siri:Monitored>
    <siri:LineRef>LINE_1</siri:LineRef>
    <siri:FramedVehicleJourneyRef>
      <siri:DatedVehicleJourneyRef>TRIP_1</siri:DatedVehicleJourneyRef>
      <siri:DataFrameRef>2026-08-09</siri:DataFrameRef>
    </siri:FramedVehicleJourneyRef>
    <siri:VehicleRef>VEHICLE_1</siri:VehicleRef>
    <siri:VehicleLocation>
      <siri:Longitude>8.55</siri:Longitude>
      <siri:Latitude>47.37</siri:Latitude>
    </siri:VehicleLocation>
    <siri:IsCompleteStopSequence>{complete_value}</siri:IsCompleteStopSequence>
    <siri:OriginRef>{origin_ref}</siri:OriginRef>
    <siri:DestinationRef>{destination_ref}</siri:DestinationRef>
    {previous_calls}
    {monitored_call}
    {onward_calls}
  </siri:MonitoredVehicleJourney>
</siri:VehicleActivity>
"""


if __name__ == "__main__":
    unittest.main()
