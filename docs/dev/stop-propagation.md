# Stop Propagation

## Overview

Trip updates can contain either a complete stop sequence or only a
partial set of stop events. `StopEventPropagationService`, orchestrated by `TripUpdateProcessingService`, handles these two cases
differently.

For a complete stop sequence, the incoming realtime stop events are
compared with the nominal GTFS stop times of the resolved trip. This
process can identify unexpected stops, add missing nominal stops,
correct stop IDs, and restore a stable output order.

For an incomplete stop sequence, the incoming events are treated as an
incremental update. If a complete sequence for the trip is already
persisted, the incoming events are merged into that sequence and delay
information is propagated through the stops between explicitly reported
events. If no complete sequence exists yet, the partial update is
persisted without inventing positions in the full trip.

The two paths are intentionally separate:

``` text
Trip Update
    |
    +-- is_complete_stop_sequence = true
    |       |
    |       +-- Load nominal GTFS stop_times
    |       +-- Propagate complete stop sequence
    |       |       +-- Detect unexpected stop occurrences
    |       |       +-- Add missing nominal stops
    |       |       +-- Optionally correct stop IDs
    |       |       +-- Order complete sequence
    |       |
    |       +-- Reassign stop_sequence from 1..N
    |
    +-- is_complete_stop_sequence = false
            |
            +-- Existing persisted complete sequence?
                    |
                    +-- yes: merge incremental events
                    |       +-- Match incoming events
                    |       +-- Replace matched event data
                    |       +-- Propagate delay between explicit updates
                    |       +-- Reassign stop_sequence from 1..N
                    |
                    +-- no: keep partial events
                            +-- Leave stop_sequence empty
```

This distinction is important. Longest Common Subsequence matching is
used for complete stop sequences only. Incremental updates continue to
use the dedicated incremental merge logic.

For the transformer-side trip-update data model, see
[transformation.md](transformation.md). For the broader differential and
incremental synchronization semantics, see
[differential-incremental.md](differential-incremental.md).

## Complete Stop Sequence Processing

A trip update with `is_complete_stop_sequence = true` is expected to
describe the complete sequence of realtime stops for the trip.

For an existing nominal trip, `DatasourceBase` loads the trip and its
`stop_times`, then passes the incoming `stop_events` and nominal stop
times to `_propagate_trip_update_stop_events`.

Nominal stop times are sorted by their GTFS `stop_sequence` before any
comparison is performed.

The complete-sequence propagation consists of these stages:

1.  Normalize nominal stop IDs for matching.
2.  Detect unexpected realtime stop occurrences when configured.
3.  Add nominal stops that are entirely missing from the realtime
    sequence.
4.  Optionally correct transmitted stop IDs to nominal stop IDs.
5.  Order the resulting events along the nominal route and merge added
    stops by time.
6.  Reassign the final `stop_sequence` values consecutively from `1` to
    `N`.

The propagation is not used for incomplete updates.

## Stop ID Normalization

Stop matching does not always compare the full transmitted stop ID
literally.

`_normalize_stop_id_for_matching` converts Global IDs to level 3 before
comparison. Non-Global-ID values are kept unchanged.

Conceptually:

``` text
full stop ID
    |
    +-- Global ID -> reduce to GlobalId level 3
    |
    +-- other ID  -> keep unchanged
```

This allows stop occurrences that refer to different lower-level
variants of the same logical stop to participate in the same matching
process.

The original/full stop IDs are still relevant for persistence, stop-ID
correction, and output ordering. The normalized value is primarily a
matching key.

## Unexpected Stop Detection

Unexpected stops can be handled as implicit GTFS-RT `ADDED` stops when
the datasource option `treat_unexpected_stop_as_added_stop` is enabled.

An unexpected stop is not limited to a stop ID that does not exist
anywhere in the nominal trip. A realtime occurrence is also unexpected
when the stop ID exists nominally but the particular occurrence cannot
be aligned with the nominal stop sequence.

This distinction matters for trips that visit the same stop more than
once or for realtime data containing duplicated or reordered stop
occurrences.

For example:

``` text
Nominal:   A -> B -> C -> D
Realtime:  A -> B -> B -> C -> D
```

A set-based comparison only observes that `B` is a nominal stop and
therefore cannot identify the second occurrence as unexpected.

Occurrence-aware matching instead allows each nominal occurrence to be
consumed at most once. One realtime `B` can match the nominal `B`; the
other occurrence remains unmatched and can be marked `ADDED`.

The same principle applies to ordering conflicts:

``` text
Nominal:   A -> B -> C -> D
Realtime:  A -> C -> B -> D
```

Not all realtime occurrences can be matched while preserving nominal
order. The alignment therefore determines which occurrences form the
best nominal subsequence and which realtime occurrences remain outside
it.

When an unmatched realtime event has a non-empty stop ID,
complete-sequence propagation sets:

``` python
event["schedule_relationship"] = "ADDED"
event["is_implied_schedule_relationship"] = True
```

The relationship is considered implied because it is derived by
`StopEventPropagationService`, not explicitly supplied by the transformer.

## Longest Common Subsequence Matching

`_match_realtime_stop_occurrences` uses a Longest Common Subsequence, or
LCS, alignment over normalized stop IDs.

The two sequences are:

``` text
Realtime:  normalized stop IDs from stop_events
Nominal:   normalized stop IDs from GTFS stop_times
```

A valid match between two occurrences requires equal normalized stop
IDs. The alignment must preserve the order of both sequences, and each
occurrence can be consumed at most once.

The primary optimization target is the number of matched stop
occurrences. In other words, the algorithm first finds an alignment with
the maximum possible LCS length.

This provides two properties that a set-based lookup cannot provide:

-   occurrence count matters;
-   occurrence order matters.

### Dynamic Programming Matrix

The implementation uses dynamic programming.

For every realtime/nominal position pair, the algorithm considers up to
three actions:

-   skip the current realtime occurrence;
-   skip the current nominal occurrence;
-   match both occurrences if their normalized stop IDs are equal.

Each matrix cell stores the best score reachable at that point and a
trace action used to reconstruct the selected alignment afterwards.

The score is a tuple with three components:

``` text
(
    structural_match_count,
    time_supported_match_count,
    negative_total_supported_time_delta
)
```

Python tuple comparison therefore applies the priorities
lexicographically.

The priorities are:

1.  maximize the number of structurally matched stop occurrences;
2.  among alignments of equal structural length, maximize the number of
    time-supported matches;
3.  among those, minimize the total scheduled departure-time difference.

This means timing information can choose between equally good structural
alignments, but cannot reduce the maximum structural LCS length.

### Scheduled Departure Time Tie-Breaking

Repeated stop IDs can produce more than one LCS with the same length.

For example:

``` text
Nominal:   A -> B -> C -> B -> D
Realtime:  A -> B -> B -> C -> D
```

There can be several ways to associate a realtime `B` occurrence with a
nominal `B` occurrence without changing the maximum number of
structurally matched stops.

To make this choice more deterministic and more closely aligned with the
timetable, the algorithm compares:

``` text
realtime stop_event.scheduled_departure_time
```

with:

``` text
nominal GTFS stop_time.departure_time
```

A match receives time support when the absolute difference is at most
120 seconds.

Formally:

``` text
abs(scheduled_departure_time - nominal departure_time) <= 120 seconds
```

The time comparison is only a tie-breaker.

A time difference greater than 120 seconds does not make two equal stop
IDs structurally incompatible. Likewise, a missing or unparsable
scheduled departure time does not prevent an otherwise valid structural
match.

This preserves the structural meaning of LCS while using planned times
to disambiguate repeated occurrences when useful.

Among time-supported alternatives, the alignment with the smaller total
departure-time difference is preferred.

### Deterministic Equal Scores

If matching the current pair produces exactly the same complete score as
the best skip alternative, the implementation prefers the concrete
match.

This keeps ordinary unique-stop sequences stable and avoids leaving a
valid occurrence unmatched when doing so provides no scoring advantage.

### LCS Result

The traceback returns the indexes of realtime events that belong to the
selected nominal alignment.

When `treat_unexpected_stop_as_added_stop` is enabled, every realtime
event with a stop ID whose index is not part of that alignment is
treated as an implicit `ADDED` stop.

The LCS result is currently used for unexpected realtime occurrence
detection. It does not replace the separate missing-stop logic described
below.

## Behavior When Added Stop Detection Is Disabled

When `treat_unexpected_stop_as_added_stop` is disabled, LCS matching is
not used.

The existing filtering behavior remains in place. Realtime events are
retained when their normalized stop ID occurs in the set of nominal
normalized stop IDs. Events whose stop ID is not nominal are removed
from the propagated sequence.

This means occurrence-aware `ADDED` detection is opt-in through the
existing datasource flag and does not change the disabled behavior.

## Missing Nominal Stops

After unexpected-stop handling, complete-sequence propagation checks
whether nominal stop IDs are absent from the realtime events.

The current missing-stop logic is ID-based. It builds a set of
normalized realtime stop IDs and iterates over the nominal stop times.

If a nominal normalized stop ID does not occur in the realtime set,
`StopEventPropagationService` creates a synthetic event from the nominal GTFS stop
time.

The generated event contains the nominal stop ID, nominal sequence,
nominal arrival and departure times, and a valid reference marker.

Its schedule relationship depends on
`treat_missing_stop_as_canceled_stop`.

When the option is enabled:

``` text
schedule_relationship = SKIPPED
is_implied_schedule_relationship = true
```

When the option is disabled:

``` text
schedule_relationship = NO_DATA
is_implied_schedule_relationship = false
```

The `SKIPPED` relationship is therefore an implied cancellation derived
from datasource configuration.

An important implementation detail is that missing-stop detection
remains ID-based rather than occurrence-based. The LCS change affects
unexpected realtime occurrences only. It does not currently cause a
second nominal occurrence of an already-present stop ID to be
synthesized when that particular occurrence is absent.

## Stop ID Correction

If `incorrect_stop_id_handling` is configured as
`FIX_TO_NOMINAL_STOP_ID`, complete-sequence propagation applies
`_apply_stop_level_stop_id_correction`.

The correction operates on normalized stop IDs while preserving
occurrence consumption.

Realtime event indexes are grouped by normalized stop ID. The nominal
stop times are then traversed in nominal order. For each nominal
occurrence, the first still-unconsumed realtime event with the same
normalized stop ID is selected.

If the transmitted full stop ID differs from the nominal full stop ID:

-   the transmitted value is retained as `original_stop_id` when not
    already present;
-   `stop_id` is replaced with the nominal full stop ID.

Each realtime event can be consumed only once by this correction pass.

This correction changes identifiers only. It does not independently add
or remove stop events.

## Complete Sequence Ordering

For a complete sequence, `_order_trip_update_stop_events` separates
events into scheduled and added events.

An event is treated as added when either:

-   its `schedule_relationship` is `ADDED`; or
-   its full stop ID is not part of the nominal full stop-ID set.

Scheduled events are sorted primarily by nominal stop rank, then by
event time, then by stop ID.

The event time used for ordering is:

``` text
departure_time, if available
otherwise arrival_time
```

Added events are sorted by event time and inserted into the scheduled
sequence before the first existing event whose event time is later.

After propagation returns, the synchronization path rewrites all
`stop_sequence` values consecutively:

``` text
1, 2, 3, ..., N
```

The resulting sequence is therefore the final propagated GTFS-RT stop
order, not necessarily the original sequence numbers supplied by the
transformer.

## Incomplete Stop Sequences

An update with `is_complete_stop_sequence = false` does not enter
complete stop propagation and does not use LCS matching.

There are two cases.

### Existing Complete Sequence

If the trip already has a persisted complete stop sequence, the incoming
partial update is merged into it using `_merge_incremental_stop_events`.

The existing complete events are first converted to dictionaries,
including:

-   `stop_id`;
-   `original_stop_id`;
-   `stop_sequence`;
-   `arrival_time`;
-   `departure_time`;
-   `scheduled_arrival_time`;
-   `scheduled_departure_time`;
-   `schedule_relationship`;
-   `is_implied_schedule_relationship`;
-   `is_valid`.

Incoming events then update their corresponding persisted occurrences.

After merging, the trip remains marked as having a complete stop
sequence and the resulting stop events are renumbered consecutively.

### No Existing Complete Sequence

If no persisted complete sequence exists yet, `TripUpdateProcessingService` cannot
infer the true position of the partial events in the full trip.

The incoming events are therefore kept as partial data and their
`stop_sequence` values are set to an empty string.

No nominal sequence is fabricated from an incomplete update.

## Incremental Stop Matching

Incremental matching is separate from complete-sequence LCS matching.

For each incoming event, `_merge_incremental_stop_events` first attempts
to match by:

``` text
normalized stop_id + transmitted stop_sequence
```

This is the primary incremental key.

If that does not resolve a match, the implementation collects
still-unconsumed persisted events with the same normalized stop ID and
calls `_resolve_incremental_match_index`.

When only one candidate exists, that occurrence is selected directly.

When several candidates share the stop ID, `_closest_by_scheduled_time`
selects the candidate whose planned time is closest to the incoming
event. The planned time prefers `scheduled_departure_time` and falls
back to `scheduled_arrival_time`.

If no reliable time signal exists, repeated occurrences fall back to
visit order by selecting the first remaining candidate.

If no persisted candidate shares the stop ID, the incremental matcher
performs a time-only search over the existing events with a 120-second
tolerance.

If no match can be resolved, the incoming event is appended as a new
event.

Every matched persisted index is consumed only once during the merge.

## Incremental Delay Propagation

After incremental events have been matched and merged,
`_propagate_incremental_delay` projects realtime delay through the
portions of the complete sequence for which no explicit update was
received.

The explicitly matched event indexes divide the sequence into
propagation segments.

For each matched reference event, the implementation determines a delay
from actual versus scheduled time.

A valid departure is preferred as the reference when its scheduled
departure is not earlier than its scheduled arrival. Otherwise, arrival
can be used when both actual and scheduled arrival are available.

The initial delay is conceptually:

``` text
current_delay = reference_actual - reference_scheduled
```

The delay is then propagated forward until the next explicitly matched
stop or the end of the sequence.

### Arrival Propagation

For an intermediate event with `scheduled_arrival_time`:

``` text
arrival_time = scheduled_arrival_time + current_delay
```

If scheduled arrival is absent but scheduled departure exists, the
departure schedule is used to produce an arrival estimate.

### Departure Propagation

For an event with `scheduled_departure_time`:

``` text
departure_estimate = scheduled_departure_time + current_delay
```

A planned dwell is treated as a timepoint when:

``` text
scheduled_departure_time > scheduled_arrival_time
```

At such a stop, an early propagated departure is not allowed to move
before the nominal scheduled departure.

Conceptually:

``` text
if timepoint and departure_estimate < scheduled_departure_time:
    departure_estimate = scheduled_departure_time
```

Late running is not clamped and continues to propagate.

The new delay for the next leg is calculated from the resulting
departure.

If only scheduled arrival exists, such as at a terminus without a
scheduled departure, the propagated arrival is mirrored to departure and
becomes the delay reference.

Propagated intermediate events receive:

``` text
schedule_relationship = SCHEDULED
```

This delay projection is an incremental-update feature and is
independent of the complete-sequence LCS alignment.

## Scheduled Time Roles

Several scheduled time fields participate in stop processing, but they
have different roles.

  --------------------------------------------------------------------------------------
  Field                        Complete Sequence  Incremental Matching Incremental Delay
                               LCS                                     Propagation
  ---------------------------- ------------------ -------------------- -----------------
  `scheduled_departure_time`   Tie-breaker        Preferred            Planned departure
                               against nominal    planned-time         and delay
                               `departure_time`   discriminator        reference

  `scheduled_arrival_time`     Not used by LCS    Fallback             Planned arrival
                                                  planned-time         and delay
                                                  discriminator        reference

  `departure_time`             Used for final     Actual               Actual departure
                               event ordering     incoming/persisted   and propagated
                                                  event value          result

  `arrival_time`               Fallback for final Actual               Actual arrival
                               event ordering     incoming/persisted   and propagated
                                                  event value          result

  Nominal GTFS                 LCS time           Not directly used by Not directly used
  `departure_time`             tie-breaker target incremental merge    by incremental
                                                                       delay propagation
  --------------------------------------------------------------------------------------

The 120-second value appears in two distinct contexts:

-   complete-sequence LCS uses it to decide whether a scheduled
    departure match receives tie-break support;
-   incremental time-only matching uses it as a maximum accepted
    difference when no same-stop candidate is available.

These mechanisms should not be conflated. In particular, the LCS
tolerance does not reject a structurally valid stop-ID match.

## Schedule Relationship Summary

Complete and incremental stop processing can affect GTFS-RT schedule
relationships as follows.

  -----------------------------------------------------------------------
  Relationship            Origin                  Meaning In Stop
                                                  Propagation
  ----------------------- ----------------------- -----------------------
  `ADDED`                 Complete-sequence       Realtime occurrence is
                          propagation             not part of the
                                                  selected nominal
                                                  alignment when
                                                  added-stop handling is
                                                  enabled

  `SKIPPED`               Complete-sequence       Nominal stop ID is
                          propagation             missing and
                                                  missing-stop
                                                  cancellation handling
                                                  is enabled

  `NO_DATA`               Complete-sequence       Nominal stop ID is
                          propagation             missing but
                                                  cancellation handling
                                                  is disabled

  `SCHEDULED`             Incremental delay       Event receives a
                          propagation             propagated
                                                  scheduled-trip
                                                  prediction
  -----------------------------------------------------------------------

For relationships inferred by datasource settings,
`is_implied_schedule_relationship` records that the relationship was
generated internally rather than supplied explicitly by the transformer.

## Examples

### Additional Occurrence Of A Nominal Stop

``` text
Nominal:
A -> B -> C -> D

Realtime:
A -> B -> B -> C -> D
```

The maximum ordered nominal alignment contains one occurrence of `B`.

With `treat_unexpected_stop_as_added_stop = true`, the unmatched
realtime `B` becomes an implied `ADDED` stop.

### Repeated Nominal Stop With Time Tie-Breaking

``` text
Nominal:
A -> B(08:10) -> C -> B(08:30) -> D

Realtime:
A -> B(08:29) -> C -> B(...) -> D
```

If several structurally equal LCS alignments are possible, the scheduled
departure times can favor the occurrence whose nominal departure is
within 120 seconds and has the smaller supported time difference.

The time information does not permit an out-of-order match and does not
reduce the structural LCS length.

### Unknown Stop ID

``` text
Nominal:
A -> B -> C -> D

Realtime:
A -> B -> X -> C -> D
```

When added-stop handling is enabled, `X` cannot match any nominal
occurrence and becomes `ADDED`.

When added-stop handling is disabled, the existing nominal-ID filtering
path removes `X`.

### Missing Nominal Stop ID

``` text
Nominal:
A -> B -> C -> D

Realtime:
A -> B -> D
```

`C` is absent from the realtime stop-ID set.

With missing-stop cancellation enabled, a nominal event for `C` is
inserted as `SKIPPED`.

Otherwise it is inserted as `NO_DATA`.

### Incremental Update

Assume a complete sequence is already persisted:

``` text
A -> B -> C -> D -> E
```

A later incomplete update reports only:

``` text
B -> D
```

The update does not run LCS propagation.

Instead, `B` and `D` are matched against the persisted sequence. Their
incoming values replace the corresponding persisted event data. Delay is
then propagated from `B` through the unreported events up to `D`, and
from `D` through the remaining sequence.

The persisted complete sequence is retained.

## Implementation Reference

The relevant implementation is located in:

``` text
backend/src/echogtfs/datasources/base.py
```

All methods in the following table are implemented by `StopEventPropagationService`. The service is deliberately separate from `MatchingService`: `MatchingService` matches realtime trips to nominal trips, while stop-occurrence matching is an internal part of stop-event reconciliation and propagation.

The main methods are:

  ----------------------------------------------------------------------------
  Method                                   Responsibility
  ---------------------------------------- -----------------------------------
  `_normalize_stop_id_for_matching`        Normalize stop IDs to the matching
                                           representation

  `_stop_event_nominal_departure_delta`    Calculate scheduled departure
                                           difference for an LCS candidate

  `_match_realtime_stop_occurrences`       Perform occurrence-aware LCS
                                           alignment with scheduled-time
                                           tie-breaking

  `_propagate_trip_update_stop_events`     Coordinate complete stop-sequence
                                           propagation

  `_apply_stop_level_stop_id_correction`   Correct matched stop IDs to nominal
                                           full IDs

  `_order_trip_update_stop_events`         Order scheduled events and merge
                                           added events by time

  `_stop_event_to_dict`                    Convert persisted events for
                                           incremental processing

  `_merge_incremental_stop_events`         Merge an incomplete update into a
                                           persisted complete sequence

  `_resolve_incremental_match_index`       Resolve ambiguous incremental stop
                                           occurrences

  `_closest_by_scheduled_time`             Select the closest planned-time
                                           candidate

  `_propagate_incremental_delay`           Project delay through unreported
                                           stops
  ----------------------------------------------------------------------------

## Design Constraints

Changes to stop propagation should preserve the separation between
complete and incomplete stop sequences.

In particular:

-   LCS-based unexpected-occurrence detection belongs to complete stop
    sequences.
-   Incomplete updates must not be interpreted as complete route
    descriptions.
-   Scheduled departure time in LCS is supporting evidence, not a
    structural matching requirement.
-   Each realtime and nominal occurrence can participate at most once in
    an LCS alignment.
-   Incremental event matching must continue to consume persisted
    candidates at most once.
-   Missing-stop propagation currently remains stop-ID based and should
    not be assumed to have occurrence-level semantics.
-   Stop-ID correction should change identifiers without independently
    changing the number of events.
-   Final `stop_sequence` values for a complete persisted sequence are
    generated from the resulting event order.
-   Existing scheduled start/end anchors must not be overwritten by an
    incomplete update.

These constraints keep complete-sequence reconciliation and incremental
prediction updates independent while allowing both paths to handle
repeated stop IDs deterministically.
