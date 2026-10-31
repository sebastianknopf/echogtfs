import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.transformers.vdv453_31_vehicle_positions_transformer import (
    Vdv453V31VehiclePositionsTransformer,
)

MODULE = "echogtfs.datasources.transformers.vdv453_31_vehicle_positions_transformer"

# 13.3377 degrees east and 52.5079 degrees north in milliseconds of arc
LONGITUDE_MS = 48015918
LATITUDE_MS = 189028512


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _activity(
    *,
    now: datetime,
    meldungsart: str = "Fahrplanlage",
    zst: datetime | None = None,
    verfall: datetime | None = None,
    trip_id: str | None = "T1",
    service_date: str | None = "2026-01-01",
    line_id: str | None = "L1",
    prognose: str | None = "true",
    longitude: str | None = str(LONGITUDE_MS),
    latitude: str | None = str(LATITUDE_MS),
    at_stop: str | None = None,
    current_stop: str | None = None,
    next_stop: str | None = None,
    fahrt_info: str | None = "",
) -> str:
    zst = zst or now
    verfall = verfall or now + timedelta(hours=1)

    parts = [f"<VISMeldungsart>{meldungsart}</VISMeldungsart><VISID>1</VISID>"]
    if trip_id is not None:
        date_xml = f"<Betriebstag>{service_date}</Betriebstag>" if service_date else ""
        parts.append(f"<FahrtID><FahrtBezeichner>{trip_id}</FahrtBezeichner>{date_xml}</FahrtID>")
    if line_id is not None:
        parts.append(f"<LinienID>{line_id}</LinienID>")
    if prognose is not None:
        parts.append(f"<PrognoseMoeglich>{prognose}</PrognoseMoeglich>")
    if current_stop:
        parts.append(f"<AktHaltID><HaltestellenID>{current_stop}</HaltestellenID></AktHaltID>")
    if at_stop is not None:
        parts.append(f"<AufHst>{at_stop}</AufHst>")
    if next_stop:
        parts.append(f"<NachHaltID><HaltestellenID>{next_stop}</HaltestellenID></NachHaltID>")
    if longitude is not None:
        parts.append(f"<Longitude>{longitude}</Longitude>")
    if latitude is not None:
        parts.append(f"<Latitude>{latitude}</Latitude>")
    if fahrt_info is not None:
        parts.append(f"<FahrtInfo>{fahrt_info}</FahrtInfo>")

    return f'<VISFahrplanlage Zst="{_iso(zst)}" VerfallZst="{_iso(verfall)}">{"".join(parts)}</VISFahrplanlage>'


def _payload(*activities: str) -> ET.Element:
    return ET.fromstring(
        "<DatenAbrufenAntwort><Bestaetigung Ergebnis=\"ok\"/><WeitereDaten>false</WeitereDaten>"
        f"<VISNachricht AboID=\"1\">{''.join(activities)}</VISNachricht></DatenAbrufenAntwort>"
    )


class TestVdv453V31VehiclePositionsTransformer(unittest.TestCase):
    def setUp(self) -> None:
        for level in ("debug", "info", "warning", "error"):
            patcher = patch(f"{MODULE}.logger.{level}")
            patcher.start()
            self.addCleanup(patcher.stop)

        self.transformer = self._transformer()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    @staticmethod
    def _transformer(**filters: list[str]) -> Vdv453V31VehiclePositionsTransformer:
        base = {"operator": [], "line": [], "legacy": []}
        base.update(filters)
        return Vdv453V31VehiclePositionsTransformer(filters=base)

    def _transform(self, *activities: str, transformer=None) -> list[dict]:
        return (transformer or self.transformer).transform({"root": _payload(*activities)})

    def _activity(self, **kwargs) -> str:
        return _activity(now=self.now, **kwargs)

    def test_empty_delivery_returns_empty_list(self) -> None:
        root = ET.fromstring("<DatenAbrufenAntwort><VISNachricht AboID=\"1\"/></DatenAbrufenAntwort>")

        self.assertEqual(self.transformer.transform({"root": root}), [])
        self.assertGreaterEqual(self.transformer.get_runtime_duration_ms(), 0.0)

    def test_parses_position_with_core_fields(self) -> None:
        result = self._transform(
            self._activity(fahrt_info="<FahrzeugID>V1</FahrzeugID>")
        )

        self.assertEqual(len(result), 1)
        record = result[0]
        self.assertFalse(record["is_deleted"])
        self.assertEqual(record["vehicle_id"], "V1")
        self.assertEqual(record["vehicle_label"], "V1")
        self.assertEqual(record["trip"]["trip_id"], "T1")
        self.assertEqual(record["trip"]["start_date"], "2026-01-01")
        self.assertEqual(record["trip"]["route_id"], "L1")
        self.assertEqual(record["trip"]["start_time"], "")
        self.assertAlmostEqual(record["longitude"], 13.3378, places=3)
        self.assertAlmostEqual(record["latitude"], 52.5079, places=3)
        self.assertEqual(record["timestamp"], self.now)
        self.assertEqual(record["trip"]["scheduled_intermediate_stops"], [])
        self.assertIsNone(record["trip"]["scheduled_start_stop_id"])
        self.assertIsNone(record["trip"]["scheduled_end_stop_id"])
        self.assertNotIn("stop_id", record)
        self.assertNotIn("current_stop_sequence", record)

    def test_vehicle_id_falls_back_to_service_date_and_trip(self) -> None:
        result = self._transform(self._activity(fahrt_info=None))

        self.assertEqual(result[0]["vehicle_id"], "2026-01-01|T1")
        self.assertIsNone(result[0]["vehicle_label"])

    def test_missing_vehicle_identity_is_discarded(self) -> None:
        self.assertEqual(self._transform(self._activity(fahrt_info=None, service_date=None)), [])

    def test_missing_required_fields_are_discarded(self) -> None:
        for kwargs in (
            {"trip_id": None},
            {"line_id": None},
            {"longitude": None},
            {"latitude": None},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self._transform(self._activity(**kwargs)), [])

    def test_invalid_coordinates_are_discarded(self) -> None:
        for kwargs in (
            {"longitude": "13.3"},
            {"longitude": "abc"},
            {"latitude": str(91 * 3_600_000)},
            {"longitude": str(181 * 3_600_000)},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self._transform(self._activity(**kwargs)), [])

    def test_expired_verfall_zst_is_discarded(self) -> None:
        activity = self._activity(verfall=self.now - timedelta(minutes=1))

        self.assertEqual(self._transform(activity), [])

    def test_stale_zst_is_discarded(self) -> None:
        activity = self._activity(zst=self.now - timedelta(minutes=6))

        self.assertEqual(self._transform(activity), [])

    def test_stop_status_at_stop(self) -> None:
        result = self._transform(
            self._activity(at_stop="true", current_stop="S1", next_stop="S2")
        )

        self.assertEqual(result[0]["current_status"], "STOPPED_AT")
        self.assertEqual(result[0]["stop_id"], "S1")

    def test_stop_status_in_transit_uses_next_stop(self) -> None:
        result = self._transform(
            self._activity(at_stop="false", current_stop="S1", next_stop="S2")
        )

        self.assertEqual(result[0]["current_status"], "IN_TRANSIT_TO")
        self.assertEqual(result[0]["stop_id"], "S2")

    def test_stop_status_in_transit_without_next_stop_has_no_stop_id(self) -> None:
        result = self._transform(self._activity(current_stop="S1"))

        self.assertEqual(result[0]["current_status"], "IN_TRANSIT_TO")
        self.assertNotIn("stop_id", result[0])

    def test_stop_status_at_stop_without_current_stop_has_no_stop_id(self) -> None:
        result = self._transform(self._activity(at_stop="true", next_stop="S2"))

        self.assertEqual(result[0]["current_status"], "IN_TRANSIT_TO")
        self.assertNotIn("stop_id", result[0])

    def test_schedule_times_require_start_time(self) -> None:
        start = self.now - timedelta(minutes=10)
        end = self.now + timedelta(minutes=30)

        complete = self._transform(
            self._activity(
                fahrt_info=(
                    f"<AbfahrtszeitStartHst>{_iso(start)}</AbfahrtszeitStartHst>"
                    f"<AnkunftszeitZielHst>{_iso(end)}</AnkunftszeitZielHst>"
                )
            )
        )[0]["trip"]
        self.assertTrue(complete["is_complete_stop_sequence"])
        self.assertEqual(complete["scheduled_start_time"], start)
        self.assertEqual(complete["scheduled_end_time"], end)

        start_only = self._transform(
            self._activity(fahrt_info=f"<AbfahrtszeitStartHst>{_iso(start)}</AbfahrtszeitStartHst>")
        )[0]["trip"]
        self.assertTrue(start_only["is_complete_stop_sequence"])
        self.assertIsNone(start_only["scheduled_end_time"])

        end_only = self._transform(
            self._activity(fahrt_info=f"<AnkunftszeitZielHst>{_iso(end)}</AnkunftszeitZielHst>")
        )[0]["trip"]
        self.assertFalse(end_only["is_complete_stop_sequence"])
        self.assertIsNone(end_only["scheduled_start_time"])
        self.assertIsNone(end_only["scheduled_end_time"])

    def _start_time_for(self, start: datetime, service_date: str | None) -> dict:
        with patch(f"{MODULE}.settings") as settings:
            settings.timezone = "Europe/Berlin"
            transformer = self._transformer()

        activity = self._activity(
            service_date=service_date,
            fahrt_info=f"<FahrzeugID>V1</FahrzeugID><AbfahrtszeitStartHst>{_iso(start)}</AbfahrtszeitStartHst>",
        )
        return transformer.transform({"root": _payload(activity), "source_name": "t"})[0]["trip"]

    def test_start_time_is_formatted_in_local_time(self) -> None:
        trip = self._start_time_for(datetime(2026, 1, 15, 8, 5, 9, tzinfo=timezone.utc), "2026-01-15")

        self.assertEqual(trip["start_time"], "09:05:09")

    def test_start_time_exceeds_24_hours_after_service_date(self) -> None:
        trip = self._start_time_for(datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc), "2026-01-15")

        self.assertEqual(trip["start_time"], "24:30:00")

    def test_start_date_falls_back_to_local_start_date(self) -> None:
        trip = self._start_time_for(datetime(2026, 1, 15, 23, 30, tzinfo=timezone.utc), None)

        self.assertEqual(trip["start_date"], "2026-01-16")
        self.assertEqual(trip["start_time"], "00:30:00")

    def test_start_time_is_empty_without_start_time(self) -> None:
        trip = self._transform(self._activity())[0]["trip"]

        self.assertEqual(trip["start_time"], "")

    def test_short_names_are_not_used_as_stop_ids(self) -> None:
        trip = self._transform(
            self._activity(
                fahrt_info="<StartHstnameKurz>A</StartHstnameKurz><ZielHstnameKurz>B</ZielHstnameKurz>"
            )
        )[0]["trip"]

        self.assertIsNone(trip["scheduled_start_stop_id"])
        self.assertIsNone(trip["scheduled_end_stop_id"])

    def test_timestamp_falls_back_to_valid_until_and_then_now(self) -> None:
        verfall = self.now + timedelta(hours=2)
        no_zst = (
            f'<VISFahrplanlage VerfallZst="{_iso(verfall)}">'
            "<VISMeldungsart>Fahrplanlage</VISMeldungsart>"
            "<FahrtID><FahrtBezeichner>T1</FahrtBezeichner><Betriebstag>2026-01-01</Betriebstag></FahrtID>"
            "<LinienID>L1</LinienID><PrognoseMoeglich>true</PrognoseMoeglich>"
            f"<Longitude>{LONGITUDE_MS}</Longitude><Latitude>{LATITUDE_MS}</Latitude>"
            "</VISFahrplanlage>"
        )
        self.assertEqual(self._transform(no_zst)[0]["timestamp"], verfall)

        no_times = no_zst.replace(f' VerfallZst="{_iso(verfall)}"', "")
        before = datetime.now(timezone.utc)
        timestamp = self._transform(no_times)[0]["timestamp"]
        self.assertGreaterEqual(timestamp, before)

    def test_naive_timestamps_are_interpreted_as_utc(self) -> None:
        activity = self._activity().replace(_iso(self.now), self.now.strftime("%Y-%m-%dT%H:%M:%S"), 1)

        self.assertEqual(self._transform(activity)[0]["timestamp"], self.now)

    def test_operator_filter_uses_fahrt_info_operator(self) -> None:
        transformer = self._transformer(operator=["op*"])

        matching = self._activity(fahrt_info="<BetreiberID>op1</BetreiberID>")
        other = self._activity(fahrt_info="<BetreiberID>xx1</BetreiberID>", trip_id="T2")
        missing = self._activity(trip_id="T3")

        result = self._transform(matching, other, missing, transformer=transformer)

        self.assertEqual([record["trip"]["trip_id"] for record in result], ["T1"])

    def test_legacy_filter_is_applied_to_operator(self) -> None:
        transformer = self._transformer(legacy=["op1"])

        result = self._transform(
            self._activity(fahrt_info="<BetreiberID>op1</BetreiberID>"),
            self._activity(fahrt_info="<BetreiberID>op2</BetreiberID>", trip_id="T2"),
            transformer=transformer,
        )

        self.assertEqual([record["trip"]["trip_id"] for record in result], ["T1"])

    def test_line_filter(self) -> None:
        transformer = self._transformer(line=["L1"])

        result = self._transform(
            self._activity(line_id="L1"),
            self._activity(line_id="L2", trip_id="T2"),
            transformer=transformer,
        )

        self.assertEqual([record["trip"]["trip_id"] for record in result], ["T1"])

    def test_removal_messages_create_deletion_records(self) -> None:
        for meldungsart in ("Fahrtabbruch", "RegulaeresFahrtende", "BereichVerlassen"):
            with self.subTest(meldungsart=meldungsart):
                result = self._transform(
                    self._activity(meldungsart=meldungsart, fahrt_info="<FahrzeugID>V1</FahrzeugID>")
                )

                self.assertEqual(
                    result,
                    [{"is_deleted": True, "vehicle_id": "V1", "trip": {"trip_id": "T1"}}],
                )

    def test_removal_bypasses_filters_and_freshness(self) -> None:
        transformer = self._transformer(operator=["op*"], line=["L9"])
        activity = self._activity(
            meldungsart="Fahrtabbruch",
            zst=self.now - timedelta(hours=1),
            verfall=self.now - timedelta(minutes=30),
        )

        result = self._transform(activity, transformer=transformer)

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_deleted"])
        self.assertEqual(result[0]["vehicle_id"], "2026-01-01|T1")

    def test_removal_without_vehicle_id_uses_trip_reference(self) -> None:
        result = self._transform(self._activity(meldungsart="Fahrtabbruch", service_date=None, fahrt_info=None))

        self.assertEqual(result, [{"is_deleted": True, "trip": {"trip_id": "T1"}}])

    def test_removal_without_identity_is_dropped(self) -> None:
        self.assertEqual(self._transform(self._activity(meldungsart="Fahrtabbruch", trip_id=None, fahrt_info=None)), [])

    def test_prognose_not_possible_creates_deletion_record(self) -> None:
        result = self._transform(self._activity(prognose="false", fahrt_info="<FahrzeugID>V1</FahrzeugID>"))

        self.assertEqual(
            result,
            [{"is_deleted": True, "vehicle_id": "V1", "trip": {"trip_id": "T1"}}],
        )

    def test_prognose_missing_counts_as_possible(self) -> None:
        result = self._transform(self._activity(prognose=None))

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["is_deleted"])

    def test_unknown_meldungsart_is_discarded(self) -> None:
        self.assertEqual(self._transform(self._activity(meldungsart="Foo")), [])

    def test_error_in_one_activity_does_not_stop_processing(self) -> None:
        original = self.transformer._resolve_stop_status
        calls = {"count": 0}

        def failing(activity):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("boom")
            return original(activity)

        self.transformer._resolve_stop_status = failing

        result = self._transform(self._activity(), self._activity(trip_id="T2"))

        self.assertEqual([record["trip"]["trip_id"] for record in result], ["T2"])


if __name__ == "__main__":
    unittest.main()
