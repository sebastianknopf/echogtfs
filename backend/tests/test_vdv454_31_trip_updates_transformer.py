import sys
import unittest
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from echogtfs.datasources.transformers.vdv454_31_trip_updates_transformer import (
    Vdv454V31TripUpdatesTransformer,
)

MODULE = "echogtfs.datasources.transformers.vdv454_31_trip_updates_transformer"

STOP_A = "xx:00001:0001:0:1"
STOP_B = "xx:00001:0002:0:1"
STOP_C = "xx:00001:0003:0:1"
STOP_D = "xx:00001:0004:0:1"


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _halt_id(stop_id: str) -> str:
    return f"<HaltID><HaltestellenID>{stop_id}</HaltestellenID></HaltID>"


def _halt(
    stop_id: str,
    *,
    arrival: datetime | None = None,
    departure: datetime | None = None,
    arrival_prediction: datetime | None = None,
    departure_prediction: datetime | None = None,
    arrival_status: str | None = "Prognose",
    departure_status: str | None = "Prognose",
    extra: str = "",
) -> str:
    parts = [_halt_id(stop_id)]
    if arrival is not None:
        parts.append(f"<Ankunftszeit>{_iso(arrival)}</Ankunftszeit>")
    if departure is not None:
        parts.append(f"<Abfahrtszeit>{_iso(departure)}</Abfahrtszeit>")
    if arrival_prediction is not None:
        parts.append(f"<IstAnkunftPrognose>{_iso(arrival_prediction)}</IstAnkunftPrognose>")
        if arrival_status:
            parts.append(f"<IstAnkunftPrognoseStatus>{arrival_status}</IstAnkunftPrognoseStatus>")
    if departure_prediction is not None:
        parts.append(f"<IstAbfahrtPrognose>{_iso(departure_prediction)}</IstAbfahrtPrognose>")
        if departure_status:
            parts.append(f"<IstAbfahrtPrognoseStatus>{departure_status}</IstAbfahrtPrognoseStatus>")
    parts.append(extra)
    return f"<IstHalt>{''.join(parts)}</IstHalt>"


def _fahrt_ref(
    *,
    trip_id: str | None = "T1",
    service_date: str | None = None,
    start_end: tuple[str, datetime, str, datetime] | None = None,
) -> str:
    inner = ""
    if trip_id is not None:
        date_xml = f"<Betriebstag>{service_date}</Betriebstag>" if service_date else ""
        inner += f"<FahrtID><FahrtBezeichner>{trip_id}</FahrtBezeichner>{date_xml}</FahrtID>"
    if start_end is not None:
        start_stop, start_time, end_stop, end_time = start_end
        inner += (
            "<FahrtStartEnde>"
            f"<StartHaltID><HaltestellenID>{start_stop}</HaltestellenID></StartHaltID>"
            f"<Startzeit>{_iso(start_time)}</Startzeit>"
            f"<EndHaltID><HaltestellenID>{end_stop}</HaltestellenID></EndHaltID>"
            f"<Endzeit>{_iso(end_time)}</Endzeit>"
            "</FahrtStartEnde>"
        )
    return f"<FahrtRef>{inner}</FahrtRef>"


def _ist_fahrt(
    *,
    fahrt_ref: str | None = None,
    line_id: str | None = "xx:line:1",
    operator_id: str | None = "OPX",
    complete: str | None = "true",
    flags: str = "",
    halts: list[str] | None = None,
) -> str:
    parts = []
    if line_id is not None:
        parts.append(f"<LinienID>{line_id}</LinienID>")
    parts.append(fahrt_ref if fahrt_ref is not None else _fahrt_ref())
    if complete is not None:
        parts.append(f"<Komplettfahrt>{complete}</Komplettfahrt>")
    if operator_id is not None:
        parts.append(f"<BetreiberID>{operator_id}</BetreiberID>")
    parts.append(flags)
    parts.extend(halts or [])
    return f"<IstFahrt>{''.join(parts)}</IstFahrt>"


def _payload(*journeys: str) -> ET.Element:
    xml = (
        "<DatenAbrufenAntwort>"
        '<Bestaetigung Zst="2030-01-01T00:00:00Z" Ergebnis="ok" Fehlernummer="0"/>'
        f'<AUSNachricht AboID="1">{"".join(journeys)}</AUSNachricht>'
        "</DatenAbrufenAntwort>"
    )
    return ET.fromstring(xml)


class TestVdv454V31TripUpdatesTransformer(unittest.TestCase):
    def setUp(self) -> None:
        self.transformer = self._transformer()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

    @staticmethod
    def _transformer(**filters: list[str]) -> Vdv454V31TripUpdatesTransformer:
        base = {"operator": [], "line": [], "legacy": []}
        base.update(filters)
        return Vdv454V31TripUpdatesTransformer(filters=base)

    def _transform(self, *journeys: str, transformer=None) -> list[dict]:
        return (transformer or self.transformer).transform({"root": _payload(*journeys)})

    def _complete_journey(self, **overrides) -> str:
        t0 = self.now + timedelta(minutes=10)
        halts = [
            _halt(STOP_A, departure=t0, departure_prediction=t0 + timedelta(minutes=2)),
            _halt(
                STOP_B,
                arrival=t0 + timedelta(minutes=5),
                departure=t0 + timedelta(minutes=6),
                arrival_prediction=t0 + timedelta(minutes=7),
                departure_prediction=t0 + timedelta(minutes=8),
            ),
            _halt(STOP_C, arrival=t0 + timedelta(minutes=10), arrival_prediction=t0 + timedelta(minutes=12)),
        ]
        kwargs = {"halts": halts}
        kwargs.update(overrides)
        return _ist_fahrt(**kwargs)

    # ------------------------------------------------------------------
    # Basic extraction
    # ------------------------------------------------------------------

    def test_empty_payload_returns_empty_list(self) -> None:
        self.assertEqual(self._transform(), [])

    def test_complete_trip_core_fields(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = self._complete_journey(
            fahrt_ref=_fahrt_ref(
                trip_id="TRIP-42",
                service_date="2030-05-06",
                start_end=(STOP_A, t0, STOP_C, t0 + timedelta(minutes=10)),
            )
        )

        trips = self._transform(journey)

        self.assertEqual(len(trips), 1)
        trip = trips[0]
        self.assertEqual(trip["trip_id"], "TRIP-42")
        self.assertFalse(trip["is_deleted"])
        self.assertEqual(trip["route_id"], "xx:line:1")
        self.assertEqual(trip["start_date"], "2030-05-06")
        self.assertEqual(trip["schedule_relationship"], "SCHEDULED")
        self.assertTrue(trip["is_complete_stop_sequence"])
        self.assertEqual(trip["scheduled_start_stop_id"], STOP_A)
        self.assertEqual(trip["scheduled_end_stop_id"], STOP_C)
        self.assertEqual(trip["scheduled_start_time"], t0)
        self.assertEqual(trip["scheduled_end_time"], t0 + timedelta(minutes=10))
        self.assertEqual(
            trip["scheduled_intermediate_stops"],
            [(STOP_B, t0 + timedelta(minutes=6))],
        )
        self.assertEqual(len(trip["stop_events"]), 3)

    def test_complete_trip_stop_events(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        trip = self._transform(self._complete_journey())[0]

        first, second, last = trip["stop_events"]
        self.assertEqual([e["stop_sequence"] for e in trip["stop_events"]], ["1", "2", "3"])

        # First stop has no arrival: arrival mirrors the departure.
        self.assertIsNone(first["scheduled_arrival_time"])
        self.assertEqual(first["scheduled_departure_time"], t0)
        self.assertEqual(first["departure_time"], t0 + timedelta(minutes=2))
        self.assertEqual(first["arrival_time"], t0 + timedelta(minutes=2))

        self.assertEqual(second["arrival_time"], t0 + timedelta(minutes=7))
        self.assertEqual(second["departure_time"], t0 + timedelta(minutes=8))
        self.assertEqual(second["scheduled_arrival_time"], t0 + timedelta(minutes=5))
        self.assertEqual(second["scheduled_departure_time"], t0 + timedelta(minutes=6))

        # Last stop has no departure: departure mirrors the arrival.
        self.assertEqual(last["arrival_time"], t0 + timedelta(minutes=12))
        self.assertEqual(last["departure_time"], t0 + timedelta(minutes=12))
        self.assertIsNone(last["scheduled_departure_time"])

        for event in trip["stop_events"]:
            self.assertEqual(event["schedule_relationship"], "SCHEDULED")

    def test_anchors_fall_back_to_first_and_last_halt_without_start_end(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        trip = self._transform(self._complete_journey())[0]

        self.assertEqual(trip["scheduled_start_stop_id"], STOP_A)
        self.assertEqual(trip["scheduled_end_stop_id"], STOP_C)
        self.assertEqual(trip["scheduled_start_time"], t0)
        self.assertEqual(trip["scheduled_end_time"], t0 + timedelta(minutes=10))

    def test_missing_prediction_falls_back_to_scheduled_and_no_data(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=5), departure=t0 + timedelta(minutes=6)),
            ]
        )

        trip = self._transform(journey)[0]

        for event in trip["stop_events"]:
            self.assertEqual(event["schedule_relationship"], "NO_DATA")
        self.assertEqual(trip["stop_events"][1]["arrival_time"], t0 + timedelta(minutes=5))
        self.assertEqual(trip["stop_events"][1]["departure_time"], t0 + timedelta(minutes=6))

    def test_unknown_prediction_status_is_ignored(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(
                    STOP_A,
                    departure=t0,
                    departure_prediction=t0 + timedelta(minutes=9),
                    departure_status="Unbekannt",
                ),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=5)),
            ]
        )

        first = self._transform(journey)[0]["stop_events"][0]

        self.assertEqual(first["departure_time"], t0)
        self.assertEqual(first["schedule_relationship"], "NO_DATA")

    def test_real_and_estimated_status_are_used_as_expected_times(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0 + timedelta(minutes=1), departure_status="Real"),
                _halt(
                    STOP_B,
                    arrival=t0 + timedelta(minutes=5),
                    arrival_prediction=t0 + timedelta(minutes=6),
                    arrival_status="Geschaetzt",
                ),
            ]
        )

        events = self._transform(journey)[0]["stop_events"]

        self.assertEqual(events[0]["departure_time"], t0 + timedelta(minutes=1))
        self.assertEqual(events[0]["schedule_relationship"], "SCHEDULED")
        self.assertEqual(events[1]["arrival_time"], t0 + timedelta(minutes=6))
        self.assertEqual(events[1]["schedule_relationship"], "SCHEDULED")

    def test_prediction_without_status_is_used(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0 + timedelta(minutes=3), departure_status=None),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=5)),
            ]
        )

        first = self._transform(journey)[0]["stop_events"][0]

        self.assertEqual(first["departure_time"], t0 + timedelta(minutes=3))
        self.assertEqual(first["schedule_relationship"], "SCHEDULED")

    # ------------------------------------------------------------------
    # Incomplete messages
    # ------------------------------------------------------------------

    def test_incomplete_trip_has_empty_stop_sequence_and_no_start_time(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            complete="false",
            fahrt_ref=_fahrt_ref(
                service_date="2030-05-06",
                start_end=(STOP_A, t0, STOP_D, t0 + timedelta(minutes=30)),
            ),
            halts=[_halt(STOP_B, departure=t0 + timedelta(minutes=5), departure_prediction=t0 + timedelta(minutes=6))],
        )

        trip = self._transform(journey)[0]

        self.assertFalse(trip["is_complete_stop_sequence"])
        self.assertIsNone(trip["start_time"])
        self.assertEqual(trip["stop_events"][0]["stop_sequence"], "")
        self.assertEqual(trip["scheduled_start_stop_id"], STOP_A)
        self.assertEqual(trip["scheduled_end_stop_id"], STOP_D)
        self.assertEqual(trip["scheduled_intermediate_stops"], [(STOP_B, t0 + timedelta(minutes=5))])

    def test_incomplete_trip_without_start_end_has_no_anchor_times(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            complete="false",
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=5), arrival_prediction=t0 + timedelta(minutes=5)),
            ],
        )

        trip = self._transform(journey)[0]

        self.assertIsNone(trip["scheduled_start_time"])
        self.assertIsNone(trip["scheduled_end_time"])
        self.assertEqual(len(trip["scheduled_intermediate_stops"]), 2)

    def test_missing_komplettfahrt_is_treated_as_incomplete(self) -> None:
        trip = self._transform(self._complete_journey(complete=None))[0]

        self.assertFalse(trip["is_complete_stop_sequence"])

    def test_incomplete_trip_in_the_past_is_kept(self) -> None:
        past = self.now - timedelta(minutes=30)
        journey = _ist_fahrt(
            complete="false",
            halts=[_halt(STOP_A, departure=past, departure_prediction=past)],
            fahrt_ref=_fahrt_ref(start_end=(STOP_A, past, STOP_B, past + timedelta(minutes=10))),
        )

        self.assertEqual(len(self._transform(journey)), 1)

    # ------------------------------------------------------------------
    # Trip relationship
    # ------------------------------------------------------------------

    def test_additional_trip_is_new_when_complete(self) -> None:
        trip = self._transform(self._complete_journey(flags="<Zusatzfahrt>true</Zusatzfahrt>"))[0]

        self.assertEqual(trip["schedule_relationship"], "NEW")

    def test_additional_trip_is_discarded_when_incomplete(self) -> None:
        journey = self._complete_journey(complete="false", flags="<Zusatzfahrt>true</Zusatzfahrt>")

        with patch(f"{MODULE}.logger.warning"):
            self.assertEqual(self._transform(journey), [])

    def test_canceled_trip(self) -> None:
        trip = self._transform(self._complete_journey(flags="<FaelltAus>true</FaelltAus>"))[0]

        self.assertEqual(trip["schedule_relationship"], "CANCELED")

    def test_additional_trip_wins_over_cancellation(self) -> None:
        flags = "<Zusatzfahrt>true</Zusatzfahrt><FaelltAus>true</FaelltAus>"
        trip = self._transform(self._complete_journey(flags=flags))[0]

        self.assertEqual(trip["schedule_relationship"], "NEW")

    def test_canceled_trip_without_halts_is_kept_with_empty_stop_events(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            flags="<FaelltAus>true</FaelltAus>",
            fahrt_ref=_fahrt_ref(start_end=(STOP_A, t0, STOP_C, t0 + timedelta(minutes=20))),
        )

        trips = self._transform(journey)

        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["schedule_relationship"], "CANCELED")
        self.assertEqual(trips[0]["stop_events"], [])
        self.assertEqual(trips[0]["scheduled_start_stop_id"], STOP_A)
        self.assertEqual(trips[0]["scheduled_end_stop_id"], STOP_C)

    def test_canceled_trip_without_halts_and_start_end_is_discarded(self) -> None:
        journey = _ist_fahrt(flags="<FaelltAus>true</FaelltAus>")

        with patch(f"{MODULE}.logger.warning"):
            self.assertEqual(self._transform(journey), [])

    def test_journey_without_halts_is_discarded(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            fahrt_ref=_fahrt_ref(start_end=(STOP_A, t0, STOP_C, t0 + timedelta(minutes=20))),
        )

        with patch(f"{MODULE}.logger.warning"):
            self.assertEqual(self._transform(journey), [])

    def test_reset_produces_deletion_record(self) -> None:
        journey = _ist_fahrt(flags="<FahrtZuruecksetzen>true</FahrtZuruecksetzen>", fahrt_ref=_fahrt_ref(trip_id="T9"))

        self.assertEqual(self._transform(journey), [{"trip_id": "T9", "is_deleted": True}])

    def test_reset_bypasses_time_window(self) -> None:
        past = self.now - timedelta(days=2)
        journey = _ist_fahrt(
            flags="<FahrtZuruecksetzen>true</FahrtZuruecksetzen>",
            halts=[_halt(STOP_A, departure=past)],
        )

        self.assertEqual(len(self._transform(journey)), 1)

    def test_reset_without_trip_id_is_discarded(self) -> None:
        journey = _ist_fahrt(
            flags="<FahrtZuruecksetzen>true</FahrtZuruecksetzen>",
            fahrt_ref=_fahrt_ref(trip_id=None),
        )

        with patch(f"{MODULE}.logger.warning"):
            self.assertEqual(self._transform(journey), [])

    # ------------------------------------------------------------------
    # Stop relationships
    # ------------------------------------------------------------------

    def test_pass_through_is_skipped(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                _halt(
                    STOP_B,
                    arrival=t0 + timedelta(minutes=5),
                    arrival_prediction=t0 + timedelta(minutes=5),
                    extra="<Durchfahrt>true</Durchfahrt>",
                ),
                _halt(STOP_C, arrival=t0 + timedelta(minutes=9), arrival_prediction=t0 + timedelta(minutes=9)),
            ]
        )

        events = self._transform(journey)[0]["stop_events"]

        self.assertEqual(events[1]["schedule_relationship"], "SKIPPED")

    def test_additional_stop_is_added(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                _halt(
                    STOP_B,
                    arrival=t0 + timedelta(minutes=5),
                    arrival_prediction=t0 + timedelta(minutes=5),
                    extra="<Zusatzhalt>true</Zusatzhalt>",
                ),
                _halt(STOP_C, arrival=t0 + timedelta(minutes=9), arrival_prediction=t0 + timedelta(minutes=9)),
            ]
        )

        events = self._transform(journey)[0]["stop_events"]

        self.assertEqual(events[1]["schedule_relationship"], "ADDED")

    def test_additional_stop_in_additional_trip_is_not_added(self) -> None:
        journey = self._complete_journey(flags="<Zusatzfahrt>true</Zusatzfahrt>")
        journey = journey.replace("</HaltID>", "</HaltID><Zusatzhalt>true</Zusatzhalt>")

        events = self._transform(journey)[0]["stop_events"]

        for event in events:
            self.assertEqual(event["schedule_relationship"], "SCHEDULED")

    def test_prediction_not_possible_ignores_predictions(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        trip = self._transform(self._complete_journey(flags="<PrognoseMoeglich>false</PrognoseMoeglich>"))[0]

        for event in trip["stop_events"]:
            self.assertEqual(event["schedule_relationship"], "NO_DATA")
        self.assertEqual(trip["stop_events"][0]["departure_time"], t0)

    def test_halts_without_stop_id_are_skipped(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                "<IstHalt><HaltID></HaltID><Abfahrtszeit>" + _iso(t0) + "</Abfahrtszeit></IstHalt>",
                _halt(STOP_C, arrival=t0 + timedelta(minutes=9), arrival_prediction=t0 + timedelta(minutes=9)),
            ]
        )

        events = self._transform(journey)[0]["stop_events"]

        self.assertEqual([e["stop_id"] for e in events], [STOP_A, STOP_C])

    # ------------------------------------------------------------------
    # Required fields
    # ------------------------------------------------------------------

    def test_missing_trip_id_is_discarded(self) -> None:
        journey = self._complete_journey(fahrt_ref=_fahrt_ref(trip_id=None))

        with patch(f"{MODULE}.logger.warning"):
            self.assertEqual(self._transform(journey), [])

    def test_missing_line_id_is_discarded(self) -> None:
        with patch(f"{MODULE}.logger.warning"):
            self.assertEqual(self._transform(self._complete_journey(line_id=None)), [])

    def test_start_date_is_derived_from_scheduled_start_when_missing(self) -> None:
        t0 = self.now + timedelta(minutes=10)
        trip = self._transform(self._complete_journey())[0]

        self.assertEqual(trip["start_date"], t0.astimezone(self.transformer._target_timezone).date().isoformat())

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def test_operator_filter_matches_wildcard(self) -> None:
        transformer = self._transformer(operator=["OP*"])

        self.assertEqual(len(self._transform(self._complete_journey(), transformer=transformer)), 1)

    def test_operator_filter_rejects_non_matching(self) -> None:
        transformer = self._transformer(operator=["OTHER*"])

        self.assertEqual(self._transform(self._complete_journey(), transformer=transformer), [])

    def test_operator_filter_rejects_missing_operator(self) -> None:
        transformer = self._transformer(operator=["OP*"])

        self.assertEqual(
            self._transform(self._complete_journey(operator_id=None), transformer=transformer),
            [],
        )

    def test_legacy_filter_is_treated_as_operator_filter(self) -> None:
        transformer = self._transformer(legacy=["OPX"])

        self.assertEqual(len(self._transform(self._complete_journey(), transformer=transformer)), 1)

    def test_line_filter_matches_and_rejects(self) -> None:
        accepted = self._transformer(line=["xx:line:*"])
        rejected = self._transformer(line=["yy:*"])

        self.assertEqual(len(self._transform(self._complete_journey(), transformer=accepted)), 1)
        self.assertEqual(self._transform(self._complete_journey(), transformer=rejected), [])

    def test_filters_use_full_match_semantics(self) -> None:
        transformer = self._transformer(line=["xx:line"])

        self.assertEqual(self._transform(self._complete_journey(), transformer=transformer), [])

    def test_filter_applies_before_reset(self) -> None:
        transformer = self._transformer(operator=["OTHER"])
        journey = _ist_fahrt(flags="<FahrtZuruecksetzen>true</FahrtZuruecksetzen>")

        self.assertEqual(self._transform(journey, transformer=transformer), [])

    # ------------------------------------------------------------------
    # Trip window
    # ------------------------------------------------------------------

    def test_complete_trip_too_far_in_future_is_discarded(self) -> None:
        t0 = self.now + timedelta(hours=3)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=5), arrival_prediction=t0 + timedelta(minutes=5)),
            ]
        )

        self.assertEqual(self._transform(journey), [])

    def test_incomplete_trip_too_far_in_future_is_discarded(self) -> None:
        t0 = self.now + timedelta(hours=3)
        journey = _ist_fahrt(complete="false", halts=[_halt(STOP_A, departure=t0, departure_prediction=t0)])

        self.assertEqual(self._transform(journey), [])

    def test_complete_trip_in_the_past_is_discarded(self) -> None:
        t0 = self.now - timedelta(hours=1)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=5), arrival_prediction=t0 + timedelta(minutes=5)),
            ]
        )

        self.assertEqual(self._transform(journey), [])

    def test_complete_trip_still_running_is_kept(self) -> None:
        t0 = self.now - timedelta(minutes=10)
        journey = _ist_fahrt(
            halts=[
                _halt(STOP_A, departure=t0, departure_prediction=t0),
                _halt(STOP_B, arrival=t0 + timedelta(minutes=20), arrival_prediction=t0 + timedelta(minutes=20)),
            ]
        )

        self.assertEqual(len(self._transform(journey)), 1)

    def test_canceled_trip_without_halts_uses_anchor_times_for_window(self) -> None:
        t0 = self.now - timedelta(hours=2)
        journey = _ist_fahrt(
            flags="<FaelltAus>true</FaelltAus>",
            fahrt_ref=_fahrt_ref(start_end=(STOP_A, t0, STOP_C, t0 + timedelta(minutes=20))),
        )

        self.assertEqual(self._transform(journey), [])

    # ------------------------------------------------------------------
    # Times
    # ------------------------------------------------------------------

    def test_naive_timestamps_are_interpreted_as_utc(self) -> None:
        parsed = Vdv454V31TripUpdatesTransformer._parse_datetime("2030-05-06T10:00:00")

        self.assertEqual(parsed, datetime(2030, 5, 6, 10, 0, tzinfo=timezone.utc))

    def test_offset_timestamps_are_converted_to_utc(self) -> None:
        parsed = Vdv454V31TripUpdatesTransformer._parse_datetime("2030-05-06T12:00:00+02:00")

        self.assertEqual(parsed, datetime(2030, 5, 6, 10, 0, tzinfo=timezone.utc))

    def test_fractional_seconds_are_supported(self) -> None:
        parsed = Vdv454V31TripUpdatesTransformer._parse_datetime("2030-05-06T10:00:00.1234Z")

        self.assertEqual(parsed, datetime(2030, 5, 6, 10, 0, 0, 123400, tzinfo=timezone.utc))

    def test_invalid_timestamp_returns_none(self) -> None:
        with patch(f"{MODULE}.logger.warning"):
            self.assertIsNone(Vdv454V31TripUpdatesTransformer._parse_datetime("not-a-date"))

    def test_start_time_formatting_in_local_timezone(self) -> None:
        with patch(f"{MODULE}.settings") as settings:
            settings.timezone = "Europe/Berlin"
            transformer = self._transformer()

        start = datetime(2030, 5, 6, 9, 4, tzinfo=timezone.utc)

        self.assertEqual(
            transformer._format_start_time(start_date="2030-05-06", scheduled_start_time=start),
            "11:04:00",
        )

    def test_start_time_uses_24h_notation_after_midnight(self) -> None:
        with patch(f"{MODULE}.settings") as settings:
            settings.timezone = "Europe/Berlin"
            transformer = self._transformer()

        start = datetime(2030, 5, 6, 22, 30, tzinfo=timezone.utc)

        self.assertEqual(
            transformer._format_start_time(start_date="2030-05-06", scheduled_start_time=start),
            "24:30:00",
        )

    def test_start_time_empty_without_scheduled_start(self) -> None:
        self.assertEqual(self.transformer._format_start_time(start_date="2030-05-06", scheduled_start_time=None), "")

    def test_unknown_timezone_falls_back_to_utc(self) -> None:
        with patch(f"{MODULE}.logger.warning"):
            zone = Vdv454V31TripUpdatesTransformer._resolve_timezone("Not/AZone")

        self.assertEqual(str(zone), "UTC")

    # ------------------------------------------------------------------
    # Robustness and runtime
    # ------------------------------------------------------------------

    def test_failing_journey_does_not_abort_other_journeys(self) -> None:
        good = self._complete_journey(fahrt_ref=_fahrt_ref(trip_id="GOOD"))
        bad = self._complete_journey(fahrt_ref=_fahrt_ref(trip_id="BAD"))
        original = self.transformer._parse_ist_fahrt

        def flaky(journey):
            if journey.findtext("FahrtRef/FahrtID/FahrtBezeichner") == "BAD":
                raise ValueError("boom")
            return original(journey)

        with patch.object(self.transformer, "_parse_ist_fahrt", side_effect=flaky), patch(f"{MODULE}.logger.error"):
            trips = self._transform(bad, good)

        self.assertEqual([t["trip_id"] for t in trips], ["GOOD"])

    def test_multiple_journeys_keep_delivery_order(self) -> None:
        first = self._complete_journey(fahrt_ref=_fahrt_ref(trip_id="A"))
        second = self._complete_journey(fahrt_ref=_fahrt_ref(trip_id="B"))

        trips = self._transform(first, second)

        self.assertEqual([t["trip_id"] for t in trips], ["A", "B"])

    def test_runtime_is_recorded(self) -> None:
        self._transform(self._complete_journey())

        self.assertGreaterEqual(self.transformer.get_runtime_duration_ms(), 0.0)


class TestVdv454V31SamplePayloads(unittest.TestCase):
    """Anonymized payloads modelled on real AUS full and incremental deliveries."""

    FULL = """<?xml version='1.0' encoding='UTF-8'?>
<DatenAbrufenAntwort>
  <Bestaetigung Zst="2030-05-06T09:11:40Z" Ergebnis="ok" Fehlernummer="0"/>
  <AUSNachricht AboID="1">
    <IstFahrt Zst="2030-05-06T09:11:40.188388Z">
      <LinienID>xx:line:100</LinienID>
      <RichtungsID>1</RichtungsID>
      <FahrtRef>
        <FahrtID>
          <FahrtBezeichner>900000001</FahrtBezeichner>
          <Betriebstag>2030-05-06</Betriebstag>
        </FahrtID>
        <FahrtStartEnde>
          <StartHaltID><HaltestellenID>xx:00001:0001:0:1</HaltestellenID></StartHaltID>
          <Startzeit>2030-05-06T09:04:00Z</Startzeit>
          <EndHaltID><HaltestellenID>xx:00001:0001:0:1</HaltestellenID></EndHaltID>
          <Endzeit>2030-05-06T09:30:00Z</Endzeit>
        </FahrtStartEnde>
      </FahrtRef>
      <Komplettfahrt>true</Komplettfahrt>
      <BetreiberID>OPX</BetreiberID>
      <IstHalt>
        <HaltID><HaltestellenID>xx:00001:0001:0:1</HaltestellenID></HaltID>
        <HaltestellenName>Fictive Stop One</HaltestellenName>
        <Abfahrtszeit>2030-05-06T09:04:00Z</Abfahrtszeit>
        <IstAbfahrtPrognose>2030-05-06T09:07:16Z</IstAbfahrtPrognose>
        <IstAbfahrtPrognoseStatus>Real</IstAbfahrtPrognoseStatus>
      </IstHalt>
      <IstHalt>
        <HaltID><HaltestellenID>xx:00001:0002:0:1</HaltestellenID></HaltID>
        <HaltestellenName>Fictive Stop Two</HaltestellenName>
        <Ankunftszeit>2030-05-06T09:05:00Z</Ankunftszeit>
        <Abfahrtszeit>2030-05-06T09:05:00Z</Abfahrtszeit>
        <IstAnkunftPrognose>2030-05-06T09:07:22Z</IstAnkunftPrognose>
        <IstAnkunftPrognoseStatus>Geschaetzt</IstAnkunftPrognoseStatus>
        <IstAbfahrtPrognose>2030-05-06T09:07:22Z</IstAbfahrtPrognose>
        <IstAbfahrtPrognoseStatus>Geschaetzt</IstAbfahrtPrognoseStatus>
      </IstHalt>
      <IstHalt>
        <HaltID><HaltestellenID>xx:00001:0003:0:1</HaltestellenID></HaltID>
        <HaltestellenName>Fictive Stop Three</HaltestellenName>
        <Ankunftszeit>2030-05-06T09:08:00Z</Ankunftszeit>
        <Abfahrtszeit>2030-05-06T09:08:00Z</Abfahrtszeit>
        <IstAnkunftPrognose>2030-05-06T09:10:00Z</IstAnkunftPrognose>
        <IstAnkunftPrognoseStatus>Prognose</IstAnkunftPrognoseStatus>
        <IstAbfahrtPrognose>2030-05-06T09:10:00Z</IstAbfahrtPrognose>
        <IstAbfahrtPrognoseStatus>Prognose</IstAbfahrtPrognoseStatus>
      </IstHalt>
      <IstHalt>
        <HaltID><HaltestellenID>xx:00001:0001:0:1</HaltestellenID></HaltID>
        <HaltestellenName>Fictive Stop One</HaltestellenName>
        <Ankunftszeit>2030-05-06T09:30:00Z</Ankunftszeit>
        <IstAnkunftPrognose>2030-05-06T09:33:00Z</IstAnkunftPrognose>
        <IstAnkunftPrognoseStatus>Prognose</IstAnkunftPrognoseStatus>
      </IstHalt>
      <PrognoseMoeglich>true</PrognoseMoeglich>
    </IstFahrt>
  </AUSNachricht>
</DatenAbrufenAntwort>"""

    INCR = """<?xml version='1.0' encoding='UTF-8'?>
<DatenAbrufenAntwort>
  <Bestaetigung Zst="2030-05-06T09:11:40Z" Ergebnis="ok" Fehlernummer="0"/>
  <AUSNachricht AboID="1">
    <IstFahrt Zst="2030-05-06T09:11:40.188388Z">
      <LinienID>xx:line:200</LinienID>
      <FahrtRef>
        <FahrtID>
          <FahrtBezeichner>900000002</FahrtBezeichner>
          <Betriebstag>2030-05-06</Betriebstag>
        </FahrtID>
        <FahrtStartEnde>
          <StartHaltID><HaltestellenID>xx:00002:0001:0:1</HaltestellenID></StartHaltID>
          <Startzeit>2030-05-06T09:28:00Z</Startzeit>
          <EndHaltID><HaltestellenID>xx:00002:0009:0:1</HaltestellenID></EndHaltID>
          <Endzeit>2030-05-06T10:24:00Z</Endzeit>
        </FahrtStartEnde>
      </FahrtRef>
      <Komplettfahrt>false</Komplettfahrt>
      <BetreiberID>OPX</BetreiberID>
      <IstHalt>
        <HaltID><HaltestellenID>xx:00002:0001:0:1</HaltestellenID></HaltID>
        <HaltestellenName>Fictive Stop Four</HaltestellenName>
        <Durchfahrt>false</Durchfahrt>
        <Aussteigeverbot>true</Aussteigeverbot>
        <Abfahrtszeit>2030-05-06T09:28:00Z</Abfahrtszeit>
        <IstAbfahrtPrognose>2030-05-06T09:28:00Z</IstAbfahrtPrognose>
        <IstAbfahrtPrognoseStatus>Prognose</IstAbfahrtPrognoseStatus>
      </IstHalt>
      <PrognoseMoeglich>true</PrognoseMoeglich>
    </IstFahrt>
    <IstFahrt Zst="2030-05-06T09:11:40.188388Z">
      <LinienID>xx:line:200</LinienID>
      <FahrtRef>
        <FahrtID>
          <FahrtBezeichner>900000003</FahrtBezeichner>
          <Betriebstag>2030-05-06</Betriebstag>
        </FahrtID>
      </FahrtRef>
      <Komplettfahrt>false</Komplettfahrt>
      <BetreiberID>OPX</BetreiberID>
      <IstHalt>
        <HaltID><HaltestellenID>xx:00002:0005:0:1</HaltestellenID></HaltID>
        <Ankunftszeit>2030-05-06T09:40:00Z</Ankunftszeit>
        <Abfahrtszeit>2030-05-06T09:41:00Z</Abfahrtszeit>
        <IstAnkunftPrognose>2030-05-06T09:42:00Z</IstAnkunftPrognose>
        <IstAnkunftPrognoseStatus>Real</IstAnkunftPrognoseStatus>
        <IstAbfahrtPrognose>2030-05-06T09:43:00Z</IstAbfahrtPrognose>
        <IstAbfahrtPrognoseStatus>Geschaetzt</IstAbfahrtPrognoseStatus>
      </IstHalt>
    </IstFahrt>
  </AUSNachricht>
</DatenAbrufenAntwort>"""

    def setUp(self) -> None:
        self.transformer = Vdv454V31TripUpdatesTransformer(
            filters={"operator": [], "line": [], "legacy": []}
        )

    def _transform(self, xml: str) -> list[dict]:
        with patch.object(Vdv454V31TripUpdatesTransformer, "_is_in_trip_window", return_value=True):
            return self.transformer.transform({"root": ET.fromstring(xml)})

    def test_full_delivery(self) -> None:
        trips = self._transform(self.FULL)

        self.assertEqual(len(trips), 1)
        trip = trips[0]
        self.assertEqual(trip["trip_id"], "900000001")
        self.assertEqual(trip["route_id"], "xx:line:100")
        self.assertEqual(trip["start_date"], "2030-05-06")
        self.assertTrue(trip["is_complete_stop_sequence"])
        # Round trip: start and end stop are identical.
        self.assertEqual(trip["scheduled_start_stop_id"], trip["scheduled_end_stop_id"])
        self.assertEqual(trip["scheduled_start_time"], datetime(2030, 5, 6, 9, 4, tzinfo=timezone.utc))
        self.assertEqual(trip["scheduled_end_time"], datetime(2030, 5, 6, 9, 30, tzinfo=timezone.utc))
        self.assertEqual(len(trip["stop_events"]), 4)
        self.assertEqual([e["stop_sequence"] for e in trip["stop_events"]], ["1", "2", "3", "4"])
        self.assertEqual(
            trip["stop_events"][0]["departure_time"],
            datetime(2030, 5, 6, 9, 7, 16, tzinfo=timezone.utc),
        )
        self.assertEqual(len(trip["scheduled_intermediate_stops"]), 2)

    def test_incremental_delivery(self) -> None:
        trips = self._transform(self.INCR)

        self.assertEqual([t["trip_id"] for t in trips], ["900000002", "900000003"])
        for trip in trips:
            self.assertFalse(trip["is_complete_stop_sequence"])
            self.assertIsNone(trip["start_time"])
            self.assertEqual(len(trip["stop_events"]), 1)
            self.assertEqual(trip["stop_events"][0]["stop_sequence"], "")

        self.assertEqual(trips[0]["scheduled_end_stop_id"], "xx:00002:0009:0:1")
        # Without FahrtStartEnde the delivered stop is used as start and end anchor.
        self.assertEqual(trips[1]["scheduled_start_stop_id"], "xx:00002:0005:0:1")
        self.assertEqual(trips[1]["scheduled_end_stop_id"], "xx:00002:0005:0:1")
        self.assertEqual(
            trips[1]["stop_events"][0]["departure_time"],
            datetime(2030, 5, 6, 9, 43, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
