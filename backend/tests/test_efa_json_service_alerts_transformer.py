from __future__ import annotations

import copy
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _service_test_bootstrap  # noqa: F401

from echogtfs.datasources.transformers.efa_json_service_alerts_transformer import (
    EfaJsonServiceAlertsTransformer,
)
from echogtfs.datasources.transformers import efa_json_service_alerts_transformer as transformer_module
from echogtfs.enum.gtfsrt import PeriodType



def _silence_logs(test_case, *modules):
    for module in modules:
        for level in ("debug", "info", "warning", "error", "exception"):
            patcher = patch.object(module.logger, level)
            patcher.start()
            test_case.addCleanup(patcher.stop)


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_info(info_type: str = "lineInfo", **overrides) -> dict:
    """Build an info object modelled on the ADDINFO example payload."""
    info = {
        "type": info_type,
        "id": "ems-11863",
        "version": 20380937,
        "priority": "high",
        "timestamps": {
            "creation": _iso(timedelta(days=-30)),
            "availability": {"from": _iso(timedelta(days=-30)), "to": _iso(timedelta(days=30))},
            "validity": [{"from": _iso(timedelta(days=-20)), "to": _iso(timedelta(days=20))}],
        },
        "infoLinks": [
            {
                "url": "https://www.stadtbus-rv-wgt.de/info",
                "subtitle": "Linien 20 und 7573.1: Streckensperrung wegen einer Baustelle",
                "content": "Zwischen <b>Ravensburg</b> und <b>Wolpertswende</b><br/>"
                "kommt es zu einer Sperrung.&nbsp;H&auml;ltte",
            }
        ],
        "properties": {
            "producerRef": "NVBW",
            "messageRef": "5344136a-6e54-550e-9310-77998a004199",
            "providerCode": "Bodensee-Oberschwaben-Verkehrsverbundgesellschaft mbH (bodo)",
        },
        "affected": {
            "lines": [{"id": "bod:05020: :R:"}, {"id": "bod:05020: :H:"}],
            "stops": [{"id": "de:08436:1"}, {"id": "de:08436:2"}],
        },
    }
    info.update(overrides)
    return info


def _make_transformer(language: str = "DE", **filters) -> EfaJsonServiceAlertsTransformer:
    all_filters = {"line": [], "operator": [], "legacy": []}
    all_filters.update(filters)
    return EfaJsonServiceAlertsTransformer(
        make_unique_id=lambda original_id, source_name: f"{source_name}:{original_id}",
        language=language,
        filters=all_filters,
    )


def _transform(infos: list, transformer: EfaJsonServiceAlertsTransformer | None = None) -> list:
    transformer = transformer or _make_transformer()
    return transformer.transform(
        {"response": {"infos": {"current": infos}}, "source_name": "efa"}
    )


def _pairs(alert: dict) -> list[tuple]:
    return [(e["stop_id"], e["route_id"]) for e in alert["informed_entities"]]


class TestEfaJsonTransformerSmoke(unittest.TestCase):
    def setUp(self):
        _silence_logs(self, transformer_module)

    def test_transforms_line_info_to_alert(self):
        alerts = _transform([_make_info()])

        self.assertEqual(len(alerts), 1)
        alert = alerts[0]
        self.assertEqual(alert["id"], "efa:5344136a-6e54-550e-9310-77998a004199")
        self.assertFalse(alert["is_deleted"])
        self.assertTrue(alert["is_active"])
        self.assertEqual(alert["cause"], "UNKNOWN_CAUSE")
        self.assertEqual(alert["effect"], "UNKNOWN_EFFECT")
        self.assertEqual(alert["severity_level"], "WARNING")
        self.assertEqual(_pairs(alert), [(None, "bod:05020: :R:"), (None, "bod:05020: :H:")])

    def test_translation_is_normalized_plain_text(self):
        translation = _transform([_make_info()])[0]["translations"][0]

        self.assertEqual(translation["language"], "DE")
        self.assertEqual(
            translation["header_text"], "Linien 20 und 7573.1: Streckensperrung wegen einer Baustelle"
        )
        self.assertNotIn("<", translation["description_text"])
        self.assertIn("Ravensburg und Wolpertswende\nkommt es", translation["description_text"])
        self.assertIn("Hältte", translation["description_text"])
        self.assertEqual(translation["url"], "https://www.stadtbus-rv-wgt.de/info")

    def test_configured_language_is_used_for_translations(self):
        alert = _transform([_make_info()], _make_transformer(language="EN"))[0]

        self.assertEqual(alert["translations"][0]["language"], "EN")

    def test_active_periods_have_expected_types(self):
        periods = _transform([_make_info()])[0]["active_periods"]

        self.assertEqual(
            [p["period_type"] for p in periods],
            [PeriodType.IMPACT_PERIOD, PeriodType.COMMUNICATION_PERIOD],
        )
        for period in periods:
            self.assertIsInstance(period["start_time"], int)
            self.assertIsInstance(period["end_time"], int)

    def test_open_end_has_no_end_time(self):
        info = _make_info()
        info["timestamps"]["validity"] = [{"from": _iso(timedelta(days=-1)), "isOpenEnd": True}]
        info["timestamps"].pop("availability")

        periods = _transform([info])[0]["active_periods"]

        self.assertEqual(len(periods), 1)
        self.assertIsNone(periods[0]["end_time"])

    def test_missing_timestamps_keeps_alert_without_periods(self):
        info = _make_info()
        info.pop("timestamps")

        alerts = _transform([info])

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["active_periods"], [])

    def test_future_window_within_limit_is_retained(self):
        info = _make_info()
        info["timestamps"] = {"availability": {"from": _iso(timedelta(days=10)), "to": _iso(timedelta(days=20))}}

        self.assertEqual(len(_transform([info])), 1)

    def test_one_valid_window_is_enough(self):
        info = _make_info()
        info["timestamps"]["availability"] = {
            "from": _iso(timedelta(days=-30)),
            "to": _iso(timedelta(days=-20)),
        }

        self.assertEqual(len(_transform([info])), 1)

    def test_runtime_duration_is_recorded(self):
        transformer = _make_transformer()
        _transform([_make_info()], transformer)

        self.assertGreaterEqual(transformer.get_runtime_duration_ms(), 0.0)

    def test_message_ref_is_preferred_over_id(self):
        alert = _transform([_make_info()])[0]
        self.assertTrue(alert["id"].endswith("5344136a-6e54-550e-9310-77998a004199"))

    def test_id_is_used_when_message_ref_is_missing(self):
        info = _make_info()
        info["properties"].pop("messageRef")

        self.assertEqual(_transform([info])[0]["id"], "efa:ems-11863")

    def test_integer_id_is_accepted_as_fallback(self):
        info = _make_info(id=4711)
        info["properties"].pop("messageRef")

        self.assertEqual(_transform([info])[0]["id"], "efa:4711")

    def test_response_without_infos_returns_no_alerts(self):
        transformer = _make_transformer()

        self.assertEqual(transformer.transform({"response": {}, "source_name": "efa"}), [])
        self.assertEqual(
            transformer.transform({"response": {"infos": {}}, "source_name": "efa"}), []
        )
        self.assertEqual(_transform([]), [])

    def test_missing_source_name_falls_back_to_default(self):
        info = _make_info()
        info["properties"].pop("messageRef")
        alerts = _make_transformer().transform(
            {"response": {"infos": {"current": [info]}}}
        )

        self.assertEqual(alerts[0]["id"], "efa-json:ems-11863")

    def test_uses_real_unique_id_helper_signature(self):
        transformer = EfaJsonServiceAlertsTransformer(
            make_unique_id=lambda original_id, source_name: uuid.uuid5(uuid.NAMESPACE_DNS, original_id),
            language="DE",
            filters={"line": [], "operator": [], "legacy": []},
        )
        alerts = transformer.transform(
            {"response": {"infos": {"current": [_make_info()]}}, "source_name": "efa"}
        )

        self.assertIsInstance(alerts[0]["id"], uuid.UUID)


class TestEfaJsonTransformerTypes(unittest.TestCase):
    def setUp(self):
        _silence_logs(self, transformer_module)

    def test_route_info_builds_stop_route_combinations(self):
        alert = _transform([_make_info("routeInfo")])[0]

        self.assertEqual(
            _pairs(alert),
            [
                ("de:08436:1", "bod:05020: :R:"),
                ("de:08436:1", "bod:05020: :H:"),
                ("de:08436:2", "bod:05020: :R:"),
                ("de:08436:2", "bod:05020: :H:"),
            ],
        )

    def test_stop_info_is_treated_like_route_info(self):
        self.assertEqual(
            _pairs(_transform([_make_info("stopInfo")])[0]),
            _pairs(_transform([_make_info("routeInfo")])[0]),
        )

    def test_stop_info_without_lines_creates_stop_only_entities(self):
        info = _make_info("stopInfo")
        info["affected"].pop("lines")

        self.assertEqual(
            _pairs(_transform([info])[0]), [("de:08436:1", None), ("de:08436:2", None)]
        )

    def test_route_info_without_stops_creates_route_only_entities(self):
        info = _make_info("routeInfo")
        info["affected"].pop("stops")

        self.assertEqual(
            _pairs(_transform([info])[0]),
            [(None, "bod:05020: :R:"), (None, "bod:05020: :H:")],
        )

    def test_line_info_ignores_stops(self):
        alert = _transform([_make_info("lineInfo")])[0]

        self.assertTrue(all(stop is None for stop, _ in _pairs(alert)))

    def test_blocking_types_behave_like_info_types(self):
        for blocking_type, info_type in (
            ("lineBlocking", "lineInfo"),
            ("routeBlocking", "routeInfo"),
            ("stopBlocking", "stopInfo"),
        ):
            with self.subTest(info_type=blocking_type):
                blocking = _transform([_make_info(blocking_type)])
                info = _transform([_make_info(info_type)])

                self.assertEqual(len(blocking), 1)
                self.assertEqual(_pairs(blocking[0]), _pairs(info[0]))

    def test_general_and_area_info_have_no_informed_entities(self):
        for info_type in ("generalInfo", "areaInfo"):
            with self.subTest(info_type=info_type):
                alerts = _transform([_make_info(info_type)])

                self.assertEqual(len(alerts), 1)
                self.assertEqual(alerts[0]["informed_entities"], [])
                self.assertEqual(len(alerts[0]["translations"]), 1)

    def test_general_info_without_affected_is_retained(self):
        info = _make_info("generalInfo")
        info.pop("affected")

        self.assertEqual(len(_transform([info])), 1)

    def test_informed_entity_has_default_flags(self):
        entity = _transform([_make_info("lineInfo")])[0]["informed_entities"][0]

        self.assertEqual(
            {k: v for k, v in entity.items() if k not in ("route_id", "stop_id")},
            {
                "agency_id": None,
                "route_type": None,
                "trip_id": None,
                "direction_id": None,
                "is_agency_valid": True,
                "is_route_valid": True,
                "is_stop_valid": True,
                "is_trip_valid": True,
            },
        )

    def test_priority_mapping(self):
        expected = {
            "veryLow": "INFO",
            "low": "INFO",
            "high": "WARNING",
            "veryHigh": "SEVERE",
            "normal": "UNKNOWN_SEVERITY",
            "bogus": "UNKNOWN_SEVERITY",
            None: "UNKNOWN_SEVERITY",
            5: "UNKNOWN_SEVERITY",
        }
        for priority, severity in expected.items():
            with self.subTest(priority=priority):
                self.assertEqual(
                    _transform([_make_info(priority=priority)])[0]["severity_level"], severity
                )

    def test_missing_priority_is_unknown_severity(self):
        info = _make_info()
        info.pop("priority")

        self.assertEqual(_transform([info])[0]["severity_level"], "UNKNOWN_SEVERITY")


class TestEfaJsonTransformerNegative(unittest.TestCase):
    def setUp(self):
        _silence_logs(self, transformer_module)

    def test_unsupported_types_are_skipped(self):
        for info_type in ("fooInfo", "", None, 42, "lineinfo", "LineInfo", "fooBlocking", ["lineInfo"]):
            with self.subTest(info_type=info_type):
                self.assertEqual(_transform([_make_info(info_type)]), [])

    def test_missing_type_is_skipped(self):
        info = _make_info()
        info.pop("type")

        self.assertEqual(_transform([info]), [])

    def test_non_object_entries_are_skipped(self):
        for entry in (None, "text", 1, [], True):
            with self.subTest(entry=entry):
                self.assertEqual(_transform([entry]), [])

    def test_valid_alerts_survive_next_to_invalid_ones(self):
        alerts = _transform([None, _make_info("fooInfo"), _make_info(), "x"])

        self.assertEqual(len(alerts), 1)

    def test_missing_identifiers_discard_alert(self):
        info = _make_info()
        info.pop("id")
        info["properties"].pop("messageRef")

        self.assertEqual(_transform([info]), [])

    def test_unusable_identifiers_discard_alert(self):
        for value in ("", "   ", None, True, 1.5, [], {}):
            with self.subTest(value=value):
                info = _make_info(id=value)
                info["properties"]["messageRef"] = value

                self.assertEqual(_transform([info]), [])

    def test_unusable_message_ref_falls_back_to_id(self):
        info = _make_info()
        info["properties"]["messageRef"] = "  "

        self.assertEqual(_transform([info])[0]["id"], "efa:ems-11863")

    def test_non_dict_properties_fall_back_to_id(self):
        info = _make_info(properties="invalid")

        self.assertEqual(_transform([info])[0]["id"], "efa:ems-11863")

    def test_missing_or_invalid_affected_discards_referencing_types(self):
        for info_type in ("lineInfo", "routeInfo", "stopInfo", "lineBlocking"):
            for affected in (None, "x", [], {}, {"lines": []}, {"lines": "x", "stops": 3}):
                with self.subTest(info_type=info_type, affected=affected):
                    info = _make_info(info_type, affected=affected)

                    self.assertEqual(_transform([info]), [])

    def test_missing_affected_key_discards_alert(self):
        info = _make_info("lineInfo")
        info.pop("affected")

        self.assertEqual(_transform([info]), [])

    def test_entries_without_usable_ids_are_ignored(self):
        info = _make_info("lineInfo", affected={"lines": [{}, {"id": ""}, {"id": None}, "x", {"id": True}]})

        self.assertEqual(_transform([info]), [])

    def test_line_info_with_only_stops_is_discarded(self):
        info = _make_info("lineInfo")
        info["affected"].pop("lines")

        self.assertEqual(_transform([info]), [])

    def test_stop_info_with_only_invalid_ids_and_valid_lines_keeps_routes(self):
        info = _make_info("stopInfo", affected={"lines": [{"id": "L1"}], "stops": [{}, {"id": " "}]})

        self.assertEqual(_pairs(_transform([info])[0]), [(None, "L1")])

    def test_numeric_ids_are_converted_to_strings(self):
        info = _make_info("lineInfo", affected={"lines": [{"id": 12}]})

        self.assertEqual(_pairs(_transform([info])[0]), [(None, "12")])

    def test_ids_are_stripped(self):
        info = _make_info("lineInfo", affected={"lines": [{"id": "  L1  "}]})

        self.assertEqual(_pairs(_transform([info])[0]), [(None, "L1")])

    def test_missing_or_invalid_info_links_discard_alert(self):
        for links in (None, [], "x", {}, [None], ["x"], [{}], [{"url": "https://a.example.com"}]):
            with self.subTest(links=links):
                self.assertEqual(_transform([_make_info(infoLinks=links)]), [])

    def test_info_link_with_only_markup_is_unusable(self):
        links = [{"subtitle": "<br/><div> </div>", "content": " \n\t "}]

        self.assertEqual(_transform([_make_info(infoLinks=links)]), [])

    def test_non_string_text_is_unusable(self):
        links = [{"subtitle": 1, "content": ["x"]}]

        self.assertEqual(_transform([_make_info(infoLinks=links)]), [])

    def test_missing_info_links_key_discards_alert(self):
        info = _make_info()
        info.pop("infoLinks")

        self.assertEqual(_transform([info]), [])

    def test_unusable_link_is_skipped_but_usable_link_kept(self):
        links = [{}, {"subtitle": "Title"}]
        translations = _transform([_make_info(infoLinks=links)])[0]["translations"]

        self.assertEqual(len(translations), 1)
        self.assertEqual(translations[0]["header_text"], "Title")
        self.assertIsNone(translations[0]["description_text"])

    def test_script_and_style_content_is_removed(self):
        links = [{"content": "Text<script>alert(1)</script><style>p{}</style>end"}]
        description = _transform([_make_info(infoLinks=links)])[0]["translations"][0][
            "description_text"
        ]

        self.assertEqual(description, "Textend")

    def test_invalid_urls_become_none(self):
        invalid_urls = [
            "http://nohost",
            "https://nohost",
            "https://nohost/path",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "example.com",
            "www.example.com",
            "//example.com",
            "https://",
            "http:///path",
            "https://exa mple.com",
            "https://example.com/a b",
            "https://example.com\\path",
            "https://example.com:99999",
            "https://example.com:0",
            "https://example.com:abc",
            "https://example.com:",
            "https://-bad.example.com",
            "https://bad-.example.com",
            "https://exa_mple.com",
            "https://example..com",
            "https://example.com/%zz",
            "https://example.com/\x00",
            "https://example.com/\nfoo",
            "https://" + "a" * 64 + ".com",
            "",
            "   ",
            None,
            42,
            ["https://example.com"],
            {"url": "https://example.com"},
        ]
        for url in invalid_urls:
            with self.subTest(url=url):
                links = [{"subtitle": "Title", "url": url}]
                translation = _transform([_make_info(infoLinks=links)])[0]["translations"][0]

                self.assertIsNone(translation["url"])

    def test_valid_urls_are_kept_trimmed(self):
        valid_urls = {
            "https://example.com": "https://example.com",
            "  http://example.com/a?b=1#c  ": "http://example.com/a?b=1#c",
            "HTTPS://Example.COM/x": "HTTPS://Example.COM/x",
            "http://127.0.0.1:8080/x": "http://127.0.0.1:8080/x",
            "http://[2001:db8::1]/x": "http://[2001:db8::1]/x",
            "https://sub.example.de:443/": "https://sub.example.de:443/",
            "https://user:pw@example.com/": "https://user:pw@example.com/",
            "https://example.com/%20a": "https://example.com/%20a",
        }
        for url, expected in valid_urls.items():
            with self.subTest(url=url):
                links = [{"subtitle": "Title", "url": url}]
                translation = _transform([_make_info(infoLinks=links)])[0]["translations"][0]

                self.assertEqual(translation["url"], expected)

    def test_expired_windows_discard_alert(self):
        info = _make_info()
        info["timestamps"] = {
            "availability": {"from": _iso(timedelta(days=-30)), "to": _iso(timedelta(days=-20))},
            "validity": [{"from": _iso(timedelta(days=-30)), "to": _iso(timedelta(days=-1))}],
        }

        self.assertEqual(_transform([info]), [])

    def test_windows_too_far_in_future_discard_alert(self):
        info = _make_info()
        info["timestamps"] = {
            "availability": {"from": _iso(timedelta(days=31)), "to": _iso(timedelta(days=40))},
            "validity": [{"from": _iso(timedelta(days=60)), "to": _iso(timedelta(days=90))}],
        }

        self.assertEqual(_transform([info]), [])

    def test_unparseable_windows_discard_alert(self):
        for window in (
            {"from": "not-a-date", "to": _iso(timedelta(days=1))},
            {"from": _iso(timedelta(days=-1)), "to": "not-a-date"},
            {"from": 12345, "to": _iso(timedelta(days=1))},
            {"to": _iso(timedelta(days=1))},
            {},
            {"from": _iso(timedelta(days=1)), "to": _iso(timedelta(days=-1))},
        ):
            with self.subTest(window=window):
                info = _make_info()
                info["timestamps"] = {"availability": window}

                self.assertEqual(_transform([info]), [])

    def test_invalid_timestamp_containers_discard_alert(self):
        for timestamps in ("x", [], 5):
            with self.subTest(timestamps=timestamps):
                self.assertEqual(_transform([_make_info(timestamps=timestamps)]), [])

        info = _make_info()
        info["timestamps"] = {"validity": "x"}
        self.assertEqual(_transform([info]), [])

        info["timestamps"] = {"availability": "x"}
        self.assertEqual(_transform([info]), [])

    def test_empty_timestamps_object_keeps_alert(self):
        alerts = _transform([_make_info(timestamps={})])

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["active_periods"], [])

    def test_open_end_with_expired_start_is_still_active(self):
        info = _make_info()
        info["timestamps"] = {
            "validity": [{"from": _iso(timedelta(days=-90)), "to": _iso(timedelta(days=-80)), "isOpenEnd": True}]
        }

        alerts = _transform([info])

        self.assertEqual(len(alerts), 1)
        self.assertIsNone(alerts[0]["active_periods"][0]["end_time"])

    def test_invalid_validity_entry_is_skipped_when_other_window_valid(self):
        info = _make_info()
        info["timestamps"]["validity"] = ["x", {"from": _iso(timedelta(days=-1)), "to": _iso(timedelta(days=1))}]

        alerts = _transform([info])

        self.assertEqual(len(alerts), 1)
        impact = [p for p in alerts[0]["active_periods"] if p["period_type"] == PeriodType.IMPACT_PERIOD]
        self.assertEqual(len(impact), 1)

    def test_naive_timestamps_are_accepted(self):
        info = _make_info()
        start = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        end = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        info["timestamps"] = {"availability": {"from": start, "to": end}}

        self.assertEqual(len(_transform([info])), 1)


class TestEfaJsonTransformerFilters(unittest.TestCase):
    def setUp(self):
        _silence_logs(self, transformer_module)

    def test_operator_filter_matches_producer_ref(self):
        transformer = _make_transformer(operator=["NVBW"])

        self.assertEqual(len(_transform([_make_info()], transformer)), 1)

    def test_operator_filter_matches_provider_code(self):
        info = _make_info()
        info["properties"]["producerRef"] = "OTHER"
        transformer = _make_transformer(operator=["Bodensee-*"])

        self.assertEqual(len(_transform([info], transformer)), 1)

    def test_legacy_filter_acts_as_operator_filter(self):
        self.assertEqual(len(_transform([_make_info()], _make_transformer(legacy=["NVBW"]))), 1)
        self.assertEqual(_transform([_make_info()], _make_transformer(legacy=["OTHER"])), [])

    def test_operator_filter_without_match_discards_alert(self):
        self.assertEqual(_transform([_make_info()], _make_transformer(operator=["OTHER"])), [])

    def test_operator_filter_is_exact_without_wildcard(self):
        self.assertEqual(_transform([_make_info()], _make_transformer(operator=["NVB"])), [])

    def test_operator_filter_discards_alert_without_provider_fields(self):
        info = _make_info()
        info["properties"] = {"messageRef": "x"}

        self.assertEqual(_transform([info], _make_transformer(operator=["NVBW"])), [])

    def test_operator_filter_ignores_blank_and_non_string_provider_values(self):
        info = _make_info()
        info["properties"]["producerRef"] = "  "
        info["properties"]["providerCode"] = 5

        self.assertEqual(_transform([info], _make_transformer(operator=["*"])), [])

    def test_line_filter_matches_route_id(self):
        transformer = _make_transformer(line=["bod:05020: :R:"])

        self.assertEqual(len(_transform([_make_info()], transformer)), 1)

    def test_line_filter_matches_stop_id(self):
        transformer = _make_transformer(line=["de:08436:2"])

        self.assertEqual(len(_transform([_make_info("stopInfo")], transformer)), 1)

    def test_line_filter_supports_wildcards(self):
        transformer = _make_transformer(line=["bod:*"])

        self.assertEqual(len(_transform([_make_info()], transformer)), 1)

    def test_line_filter_without_match_discards_alert(self):
        transformer = _make_transformer(line=["missing"])

        self.assertEqual(_transform([_make_info("stopInfo")], transformer), [])

    def test_line_filter_does_not_match_stops_of_line_info(self):
        transformer = _make_transformer(line=["de:08436:1"])

        self.assertEqual(_transform([_make_info("lineInfo")], transformer), [])

    def test_line_filter_discards_entityless_alerts(self):
        transformer = _make_transformer(line=["*"])

        self.assertEqual(_transform([_make_info("generalInfo")], transformer), [])

    def test_operator_and_line_filters_must_both_match(self):
        self.assertEqual(
            _transform([_make_info()], _make_transformer(operator=["OTHER"], line=["bod:*"])), []
        )
        self.assertEqual(
            _transform([_make_info()], _make_transformer(operator=["NVBW"], line=["nope"])), []
        )
        self.assertEqual(
            len(_transform([_make_info()], _make_transformer(operator=["NVBW"], line=["bod:*"]))), 1
        )

    def test_filter_selects_only_matching_alerts(self):
        other = _make_info()
        other["properties"] = {"messageRef": "other", "producerRef": "OTHER"}
        transformer = _make_transformer(operator=["NVBW"])

        alerts = _transform([other, _make_info()], transformer)

        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]["id"].endswith("5344136a-6e54-550e-9310-77998a004199"))


class TestEfaJsonTransformerInvalidInput(unittest.TestCase):
    def setUp(self):
        _silence_logs(self, transformer_module)

    def test_invalid_language_is_rejected(self):
        for language in ("de-DE", "en-GB", "en-US", "de", "FR", "", None):
            with self.subTest(language=language):
                with self.assertRaises(ValueError):
                    _make_transformer(language=language)

    def test_supported_languages(self):
        self.assertEqual(EfaJsonServiceAlertsTransformer.SUPPORTED_LANGUAGES, ("DE", "EN"))

    def test_invalid_raw_data_is_rejected(self):
        transformer = _make_transformer()
        for raw in (None, [], "x", {}, {"response": None}, {"response": []}, {"response": "x"}):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    transformer.transform(raw)

    def test_invalid_infos_structure_is_rejected(self):
        transformer = _make_transformer()
        for infos in (None, [], "x", {"current": None}, {"current": {}}, {"current": "x"}):
            with self.subTest(infos=infos):
                with self.assertRaises(ValueError):
                    transformer.transform({"response": {"infos": infos}, "source_name": "efa"})

    def test_runtime_is_recorded_after_failure(self):
        transformer = _make_transformer()
        with self.assertRaises(ValueError):
            transformer.transform(None)

        self.assertGreaterEqual(transformer.get_runtime_duration_ms(), 0.0)

    def test_input_is_not_mutated(self):
        infos = [_make_info("routeInfo")]
        snapshot = copy.deepcopy(infos)

        _transform(infos)

        self.assertEqual(infos, snapshot)


if __name__ == "__main__":
    unittest.main()
