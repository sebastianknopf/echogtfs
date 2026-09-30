from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from echogtfs.common.global_id import GlobalId
from echogtfs.enum.system import IncorrectStopIdHandling

logger = logging.getLogger("uvicorn")


class StopEventPropagationService:
    """Matches and propagates stop events within an already identified trip."""

    @staticmethod
    def _coerce_stop_time_for_sort(value: Any) -> datetime:
        """Best-effort datetime conversion used only for stop-event merge ordering."""
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                return datetime.max.replace(tzinfo=timezone.utc)

        return datetime.max.replace(tzinfo=timezone.utc)

    @staticmethod
    def _normalize_stop_id_for_matching(value: Any) -> str:
        """Normalize a stop ID to its level-3 global-ID form for matching purposes."""
        if value is None:
            return ""

        stop_id = str(value)
        if not stop_id:
            return ""

        if GlobalId.is_global_id(stop_id):
            return GlobalId.level(stop_id, 3)

        return stop_id

    @staticmethod
    def _nominal_stop_sequence(stop_time: Any) -> int:
        """Return a sortable stop_sequence, placing unparsable values last."""
        try:
            return int(stop_time.stop_sequence)
        except (AttributeError, TypeError, ValueError):
            return sys.maxsize

    def _stop_event_nominal_departure_delta(
        self,
        event: dict[str, Any],
        stop_time: Any,
    ) -> float | None:
        """Return the absolute planned-departure delta in seconds for one stop match."""
        event_time = self._coerce_stop_time_for_sort(event.get("scheduled_departure_time"))
        nominal_time = self._coerce_stop_time_for_sort(getattr(stop_time, "departure_time", None))
        max_time = datetime.max.replace(tzinfo=timezone.utc)
        if event_time == max_time or nominal_time == max_time:
            return None

        return abs((event_time - nominal_time).total_seconds())

    def _match_realtime_stop_occurrences(
        self,
        stop_events: list[dict[str, Any]],
        nominal_stop_times: list[Any],
        *,
        scheduled_time_tolerance_seconds: float = 120.0,
    ) -> set[int]:
        """Return realtime indexes belonging to the best ordered nominal-stop alignment.

        Matching is a longest-common-subsequence alignment over normalized stop IDs,
        so every nominal and realtime stop occurrence can be consumed at most once.
        If several alignments contain the same number of stops, scheduled departure
        times within ``scheduled_time_tolerance_seconds`` are used only as a
        tie-breaker.
        """
        realtime_ids = [
            self._normalize_stop_id_for_matching(event.get("stop_id"))
            for event in stop_events
        ]
        nominal_ids = [
            self._normalize_stop_id_for_matching(stop_time.stop_id)
            for stop_time in nominal_stop_times
        ]

        realtime_count = len(stop_events)
        nominal_count = len(nominal_stop_times)

        # Score components, in priority order:
        # 1. number of structurally matched stops (the LCS length),
        # 2. number of matches whose scheduled departure is within tolerance,
        # 3. smallest total departure-time delta among those time-supported matches.
        dp: list[list[tuple[int, int, float]]] = [
            [(0, 0, 0.0) for _ in range(nominal_count + 1)]
            for _ in range(realtime_count + 1)
        ]
        
        trace: list[list[str | None]] = [
            [None for _ in range(nominal_count + 1)]
            for _ in range(realtime_count + 1)
        ]

        for realtime_index in range(1, realtime_count + 1):
            trace[realtime_index][0] = "realtime"
        for nominal_index in range(1, nominal_count + 1):
            trace[0][nominal_index] = "nominal"

        for realtime_index in range(1, realtime_count + 1):
            for nominal_index in range(1, nominal_count + 1):
                best_score = dp[realtime_index - 1][nominal_index]
                best_action = "realtime"

                nominal_skip_score = dp[realtime_index][nominal_index - 1]
                if nominal_skip_score > best_score:
                    best_score = nominal_skip_score
                    best_action = "nominal"

                realtime_stop_id = realtime_ids[realtime_index - 1]
                nominal_stop_id = nominal_ids[nominal_index - 1]
                if realtime_stop_id and realtime_stop_id == nominal_stop_id:
                    previous_score = dp[realtime_index - 1][nominal_index - 1]
                    delta = self._stop_event_nominal_departure_delta(
                        stop_events[realtime_index - 1],
                        nominal_stop_times[nominal_index - 1],
                    )
                    
                    time_supported = (
                        delta is not None
                        and delta <= scheduled_time_tolerance_seconds
                    )
                    
                    match_score = (
                        previous_score[0] + 1,
                        previous_score[1] + (1 if time_supported else 0),
                        previous_score[2] - (delta if time_supported and delta is not None else 0.0),
                    )

                    # Prefer consuming a concrete occurrence when all score
                    # components are equal. This keeps unique-stop sequences stable.
                    if match_score >= best_score:
                        best_score = match_score
                        best_action = "match"

                dp[realtime_index][nominal_index] = best_score
                trace[realtime_index][nominal_index] = best_action

        matched_realtime_indexes: set[int] = set()
        realtime_index = realtime_count
        nominal_index = nominal_count
        while realtime_index > 0 or nominal_index > 0:
            action = trace[realtime_index][nominal_index]
            if action == "match":
                matched_realtime_indexes.add(realtime_index - 1)
                realtime_index -= 1
                nominal_index -= 1
            elif action == "realtime":
                realtime_index -= 1
            elif action == "nominal":
                nominal_index -= 1
            else:
                break

        return matched_realtime_indexes

    def _propagate_trip_update_stop_events(
        self,
        stop_events: list[dict[str, Any]],
        nominal_stop_times: list[Any],
        *,
        treat_unexpected_stop_as_added_stop: bool,
        treat_missing_stop_as_canceled_stop: bool,
        is_complete_stop_sequence: bool,
        incorrect_stop_id_handling: IncorrectStopIdHandling = IncorrectStopIdHandling.IGNORE,
    ) -> list[dict[str, Any]]:
        """Apply nominal-stop propagation and merge rules for one trip-update stop-event list."""
        if not nominal_stop_times:
            return [dict(event) for event in stop_events]

        nominal_stop_times = sorted(nominal_stop_times, key=self._nominal_stop_sequence)
        propagated_events = [dict(event) for event in stop_events]

        nominal_stop_ids_for_matching: set[str] = set()
        nominal_full_ids: set[str] = set()
        nominal_order: list[str] = []
        for stop_time in nominal_stop_times:
            full_stop_id = str(stop_time.stop_id)
            reduced_stop_id = self._normalize_stop_id_for_matching(stop_time.stop_id)

            if reduced_stop_id not in nominal_stop_ids_for_matching:
                nominal_stop_ids_for_matching.add(reduced_stop_id)

            if full_stop_id not in nominal_full_ids:
                nominal_full_ids.add(full_stop_id)
                nominal_order.append(full_stop_id)

        if treat_unexpected_stop_as_added_stop:
            matched_realtime_indexes = self._match_realtime_stop_occurrences(
                propagated_events,
                nominal_stop_times,
            )
            
            for index, event in enumerate(propagated_events):
                stop_id = self._normalize_stop_id_for_matching(event.get("stop_id"))
                if stop_id and index not in matched_realtime_indexes:
                    event["schedule_relationship"] = "ADDED"
                    event["is_implied_schedule_relationship"] = True
        else:
            propagated_events = [
                event
                for event in propagated_events
                if self._normalize_stop_id_for_matching(event.get("stop_id"))
                in nominal_stop_ids_for_matching
            ]

        realtime_stop_ids = {
            self._normalize_stop_id_for_matching(event.get("stop_id"))
            for event in propagated_events
            if event.get("stop_id")
        }

        for stop_time in nominal_stop_times:
            nominal_stop_id = self._normalize_stop_id_for_matching(stop_time.stop_id)
            if nominal_stop_id in realtime_stop_ids:
                continue

            propagated_events.append(
                {
                    "stop_id": str(stop_time.stop_id),
                    "original_stop_id": str(stop_time.stop_id),
                    "stop_sequence": str(stop_time.stop_sequence),
                    "arrival_time": stop_time.arrival_time,
                    "departure_time": stop_time.departure_time,
                    "schedule_relationship": "SKIPPED" if treat_missing_stop_as_canceled_stop else "NO_DATA",
                    "is_implied_schedule_relationship": bool(treat_missing_stop_as_canceled_stop),
                    "is_valid": True,
                }
            )
            
            realtime_stop_ids.add(nominal_stop_id)

        if incorrect_stop_id_handling == IncorrectStopIdHandling.FIX_TO_NOMINAL_STOP_ID:
            propagated_events = self._apply_stop_level_stop_id_correction(
                propagated_events,
                nominal_stop_times,
            )

        if not is_complete_stop_sequence:
            return propagated_events

        return self._order_trip_update_stop_events(propagated_events, nominal_order)

    def _apply_stop_level_stop_id_correction(
        self,
        stop_events: list[dict[str, Any]],
        nominal_stop_times: list[Any],
    ) -> list[dict[str, Any]]:
        """Fix matched stop IDs at stop level without changing stop add/remove behavior."""
        corrected_events = [dict(event) for event in stop_events]

        remaining_event_indexes_by_reduced: dict[str, list[int]] = {}
        for index, event in enumerate(corrected_events):
            schedule_relationship = str(event.get("schedule_relationship") or "").upper()
            is_implied_schedule_relationship = bool(event.get("is_implied_schedule_relationship", False))
            if is_implied_schedule_relationship and schedule_relationship in {"ADDED", "SKIPPED"}:
                continue

            reduced_stop_id = self._normalize_stop_id_for_matching(event.get("stop_id"))
            if not reduced_stop_id:
                continue

            remaining_event_indexes_by_reduced.setdefault(reduced_stop_id, []).append(index)

        matched_event_indexes: set[int] = set()
        for stop_time in nominal_stop_times:
            nominal_full_stop_id = str(stop_time.stop_id)
            nominal_reduced_stop_id = self._normalize_stop_id_for_matching(nominal_full_stop_id)
            if not nominal_reduced_stop_id:
                continue

            candidate_indexes = remaining_event_indexes_by_reduced.get(nominal_reduced_stop_id) or []
            matched_index = None
            while candidate_indexes:
                candidate_index = candidate_indexes.pop(0)
                if candidate_index not in matched_event_indexes:
                    matched_index = candidate_index
                    break

            if matched_index is None:
                continue

            matched_event_indexes.add(matched_index)
            matched_event = corrected_events[matched_index]
            transmitted_stop_id = matched_event.get("stop_id")
            if transmitted_stop_id is None:
                matched_event["stop_id"] = nominal_full_stop_id
                matched_event.setdefault("original_stop_id", nominal_full_stop_id)
                continue

            transmitted_stop_id_str = str(transmitted_stop_id)
            if transmitted_stop_id_str != nominal_full_stop_id:
                matched_event.setdefault("original_stop_id", transmitted_stop_id_str)
                matched_event["stop_id"] = nominal_full_stop_id

        return corrected_events

    def _order_trip_update_stop_events(
        self,
        stop_events: list[dict[str, Any]],
        nominal_order: list[str],
    ) -> list[dict[str, Any]]:
        """Order stop events along the nominal sequence and merge ADDED stops by time."""
        nominal_rank = {stop_id: index for index, stop_id in enumerate(nominal_order)}
        nominal_stop_ids = set(nominal_order)

        added_events: list[dict[str, Any]] = []
        scheduled_events: list[dict[str, Any]] = []
        for event in stop_events:
            stop_id = str(event.get("stop_id") or "")
            if (
                str(event.get("schedule_relationship") or "").upper() == "ADDED"
                or (stop_id and stop_id not in nominal_stop_ids)
            ):
                added_events.append(event)
            else:
                scheduled_events.append(event)

        def event_time(event: dict[str, Any]) -> datetime:
            return self._coerce_stop_time_for_sort(
                event.get("departure_time") or event.get("arrival_time")
            )

        def scheduled_sort_key(event: dict[str, Any]) -> tuple[int, datetime, str]:
            stop_id = str(event.get("stop_id") or "")
            
            return (
                nominal_rank.get(stop_id, len(nominal_order)),
                event_time(event),
                stop_id,
            )

        ordered_events = sorted(scheduled_events, key=scheduled_sort_key)

        for added_event in sorted(added_events, key=event_time):
            added_time = event_time(added_event)
            insert_index = len(ordered_events)
            for index, existing_event in enumerate(ordered_events):
                if event_time(existing_event) > added_time:
                    insert_index = index
                    break

            ordered_events.insert(insert_index, added_event)

        return ordered_events

    @staticmethod
    def _stop_event_to_dict(event: Any) -> dict[str, Any]:
        """Convert a persisted StopEvent row into a plain dict for merge processing."""
        return {
            "stop_id": event.stop_id,
            "original_stop_id": event.original_stop_id,
            "stop_sequence": event.stop_sequence,
            "arrival_time": event.arrival_time,
            "departure_time": event.departure_time,
            "scheduled_arrival_time": event.scheduled_arrival_time,
            "scheduled_departure_time": event.scheduled_departure_time,
            "schedule_relationship": event.schedule_relationship,
            "is_implied_schedule_relationship": event.is_implied_schedule_relationship,
            "is_valid": event.is_valid,
        }

    def _merge_incremental_stop_events(
        self,
        existing_stop_events: list[dict[str, Any]],
        incoming_stop_events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Merge a partial (incomplete) stop-event update into an already-complete sequence.

        Incoming stops overwrite their matched counterparts; stops between/after matched
        stops are re-projected using the delay carried forward from the nearest preceding
        matched stop, converging back to nominal times at stops with planned dwell time
        (timepoints).
        """
        if not existing_stop_events:
            return [dict(event) for event in incoming_stop_events]

        merged_events = [dict(event) for event in existing_stop_events]

        candidates_by_stop_id: dict[str, list[int]] = {}
        index_by_stop_and_sequence: dict[tuple[str, str], int] = {}
        for index, event in enumerate(merged_events):
            reduced_stop_id = self._normalize_stop_id_for_matching(event.get("stop_id"))
            if not reduced_stop_id:
                continue

            candidates_by_stop_id.setdefault(reduced_stop_id, []).append(index)
            stop_sequence = event.get("stop_sequence")
            if stop_sequence is not None:
                index_by_stop_and_sequence[(reduced_stop_id, str(stop_sequence))] = index

        matched_indexes: set[int] = set()

        for incoming_event in incoming_stop_events:
            reduced_stop_id = self._normalize_stop_id_for_matching(incoming_event.get("stop_id"))
            incoming_sequence = incoming_event.get("stop_sequence")

            # Primary match key: stop_id + stop_sequence delivered by the transformer.
            match_index = None
            if reduced_stop_id and incoming_sequence:
                candidate_index = index_by_stop_and_sequence.get((reduced_stop_id, str(incoming_sequence)))
                if candidate_index is not None and candidate_index not in matched_indexes:
                    match_index = candidate_index

            # Fallback: stop_sequence not available/usable, match by planned time instead.
            if match_index is None:
                candidates = [
                    index for index in candidates_by_stop_id.get(reduced_stop_id, [])
                    if index not in matched_indexes
                ]
                match_index = self._resolve_incremental_match_index(merged_events, incoming_event, candidates)

            if match_index is None:
                merged_events.append(dict(incoming_event))
                match_index = len(merged_events) - 1

            merged_events[match_index].update(incoming_event)
            matched_indexes.add(match_index)

        if matched_indexes:
            self._propagate_incremental_delay(merged_events, matched_indexes)

        return merged_events

    def _resolve_incremental_match_index(
        self,
        existing_events: list[dict[str, Any]],
        incoming_event: dict[str, Any],
        candidates: list[int],
    ) -> int | None:
        """Match by planned departure/arrival time, used only when stop_sequence didn't resolve."""
        if len(candidates) == 1:
            return candidates[0]

        if candidates:
            best_index = self._closest_by_scheduled_time(existing_events, incoming_event, candidates)
            # Same stop visited more than once (e.g. round trip); fall back to visit order
            # when there is no reliable time signal to disambiguate.
            return best_index if best_index is not None else candidates[0]

        # No candidate shares the stop_id (e.g. remapped identifier); try time-only matching.
        return self._closest_by_scheduled_time(existing_events, incoming_event, range(len(existing_events)), tolerance_seconds=120)

    def _closest_by_scheduled_time(
        self,
        existing_events: list[dict[str, Any]],
        incoming_event: dict[str, Any],
        candidates: Any,
        *,
        tolerance_seconds: float | None = None,
    ) -> int | None:
        """Return the candidate index whose planned departure time is closest to the incoming event's."""
        incoming_time = self._coerce_stop_time_for_sort(
            incoming_event.get("scheduled_departure_time") or incoming_event.get("scheduled_arrival_time")
        )
        if incoming_time == datetime.max:
            return None

        best_index = None
        best_delta = None
        for index in candidates:
            candidate_time = self._coerce_stop_time_for_sort(
                existing_events[index].get("scheduled_departure_time")
                or existing_events[index].get("scheduled_arrival_time")
            )
            
            if candidate_time == datetime.max:
                continue

            delta = abs((candidate_time - incoming_time).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_index = index

        if tolerance_seconds is not None and (best_delta is None or best_delta > tolerance_seconds):
            return None

        return best_index

    def _propagate_incremental_delay(
        self,
        stop_events: list[dict[str, Any]],
        matched_indexes: set[int],
    ) -> None:
        """Continue the delay prognosis segment-by-segment using only each stop's own scheduled_* data.

        Starting from an explicitly reported stop, the chain runs departure(0) -> arrival(1) ->
        departure(1) -> arrival(2) -> departure(2) -> ... up to the next explicitly reported stop
        (or the trip's last stop). A planned dwell (timepoint, i.e. scheduled arrival < scheduled
        departure) tries to converge back towards the nominal departure: running early is floored
        to 0 delay there, while running late is never clamped and keeps propagating.
        """
        sorted_matched = sorted(matched_indexes)

        for position, matched_index in enumerate(sorted_matched):
            segment_end = sorted_matched[position + 1] if position + 1 < len(sorted_matched) else len(stop_events)
            if segment_end <= matched_index + 1:
                continue

            reference_event = stop_events[matched_index]
            ref_scheduled_arrival = self._coerce_datetime(reference_event.get("scheduled_arrival_time"))
            ref_scheduled_departure = self._coerce_datetime(reference_event.get("scheduled_departure_time"))
            ref_actual_arrival = self._coerce_datetime(reference_event.get("arrival_time"))
            ref_actual_departure = self._coerce_datetime(reference_event.get("departure_time"))

            # A departure earlier than its own arrival is not a valid dwell; such inconsistent
            # data is ignored in favor of the (always reliable) arrival for the delay reference.
            departure_is_valid_reference = ref_scheduled_departure is not None and (
                ref_scheduled_arrival is None or ref_scheduled_departure >= ref_scheduled_arrival
            )

            if departure_is_valid_reference and ref_actual_departure is not None:
                reference_actual = ref_actual_departure
                reference_scheduled = ref_scheduled_departure
            elif ref_actual_arrival is not None and ref_scheduled_arrival is not None:
                reference_actual = ref_actual_arrival
                reference_scheduled = ref_scheduled_arrival
            else:
                continue

            # Delay carried forward from the reference stop's departure.
            current_delay = reference_actual - reference_scheduled

            for index in range(matched_index + 1, segment_end):
                event = stop_events[index]
                scheduled_arrival = self._coerce_datetime(event.get("scheduled_arrival_time"))
                scheduled_departure = self._coerce_datetime(event.get("scheduled_departure_time"))

                if scheduled_arrival is None and scheduled_departure is None:
                    continue

                # Step: departure(previous) -> arrival(this stop).
                if scheduled_arrival is not None:
                    event["arrival_time"] = scheduled_arrival + current_delay
                elif scheduled_departure is not None:
                    # Origin-like stop with no scheduled arrival: mirror the departure step,
                    # same as the transformer does when only one actual time is delivered.
                    event["arrival_time"] = scheduled_departure + current_delay

                # Step: arrival(this stop) -> departure(this stop); a timepoint dwell converges
                # back towards the nominal departure when running early, never when running late.
                if scheduled_departure is not None:
                    departure_estimate = scheduled_departure + current_delay

                    is_timepoint = scheduled_arrival is not None and scheduled_departure > scheduled_arrival
                    if is_timepoint and departure_estimate < scheduled_departure:
                        departure_estimate = scheduled_departure

                    event["departure_time"] = departure_estimate
                    current_delay = departure_estimate - scheduled_departure
                elif scheduled_arrival is not None:
                    # Terminus/no-departure stop: mirror the propagated arrival, same as the
                    # transformer does when only one of the two actual times is delivered.
                    event["departure_time"] = event["arrival_time"]
                    current_delay = event["arrival_time"] - scheduled_arrival

                event["schedule_relationship"] = "SCHEDULED"
