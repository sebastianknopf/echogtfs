(h-conflicts-types)=

# Konflikttypen

Diese Seite beschreibt alle Konflikttypen, die im {ref}`Konfliktmonitoring <h-conflicts-conflicts>` auftreten können, sowie die Umstände, unter denen sie jeweils erzeugt werden. Jeder Konflikt wird entweder als **Fehler** oder als **Warnung** eingestuft.

## Fehler

- **ERROR_DATASOURCE_FAILURE**: Eine Datenquelle ist mindestens fünfmal in Folge fehlgeschlagen, oder eine zeitbasierte Datenquelle hat ihren nächsten, über den Cron-Ausdruck erwarteten Lauf um mehr als 5 Minuten überschritten.
- **ERROR_NO_AGENCY_FOUND**: Eine Meldung verweist auf eine Verkehrsunternehmen-ID, die nach dem Mapping keinem Verkehrsunternehmen im GTFS-Feed entspricht.
- **ERROR_NO_ROUTE_FOUND**: Eine Meldung, eine Fahrt oder eine Fahrzeugposition verweist auf eine Linien-ID, die nach dem Mapping keiner Linie im GTFS-Feed entspricht.
- **ERROR_NO_STOP_FOUND**: Eine Meldung, ein Halteereignis einer Fahrt oder die aktuelle Haltestelle einer Fahrzeugposition verweist auf eine Haltestellen-ID, die nach dem Mapping keiner Haltestelle im GTFS-Feed entspricht.
- **ERROR_NO_TRIP_FOUND**: Eine Meldung, eine Fahrt oder eine Fahrzeugposition verweist auf eine Fahrt-ID, die weder direkt noch über das Matching einer Fahrt im GTFS-Feed zugeordnet werden kann.

## Warnungen

- **WARNING_IMPLIED_ADDITIONAL_STOP**: Ein Halteereignis einer Fahrt wurde vom System automatisch als Zusatzhalt eingestuft, weil die Haltestelle nicht im geplanten Fahrtverlauf enthalten ist. _Dieser Konflikt tritt nur auf, wenn an der Datenquelle die Option **Unerwartete Halte als Zusatzhalt behandeln** aktiviert ist._
- **WARNING_IMPLIED_CANCELED_STOP**: Ein geplanter Halt einer Fahrt wurde vom System automatisch als Haltausfall eingestuft, weil die Haltestelle in den übermittelten Daten fehlt. _Dieser Konflikt tritt nur auf, wenn an der Datenquelle die Option **Fehlende Halte als Haltausfall behandeln** aktiviert ist._
- **WARNING_WRONG_QUAY**: Die von der Datenquelle übermittelte Haltestellen-ID eines Halteereignisses wurde vom System auf die geplante Haltestellen-ID korrigiert. _Dieser Konflikt tritt nur auf, wenn an der Datenquelle beim **Umgang mit fehlerhafter Halt-ID** die Option **Auf Soll-Halt-ID korrigieren** eingestellt ist._
- **WARNING_AGENCY_NO_GLOBAL_ID**: Die Verkehrsunternehmen-ID entspricht nicht dem konfigurierten Muster für globale IDs.
- **WARNING_ROUTE_NO_GLOBAL_ID**: Die Linien-ID entspricht nicht dem konfigurierten Muster für globale IDs.
- **WARNING_STOP_NO_GLOBAL_ID**: Die Haltestellen-ID entspricht nicht dem konfigurierten Muster für globale IDs.
- **WARNING_TRIP_NO_GLOBAL_ID**: Die Fahrt-ID entspricht nicht dem konfigurierten Muster für globale IDs.
- **WARNING_PREMATURE_DEPARTURE**: Ein Halteereignis einer Fahrt enthält eine Abfahrtszeit, die vor der Ankunftszeit an derselben Haltestelle liegt.

```{note}
Die Warnungen zu globalen IDs beziehen sich immer auf die ursprünglich von der Datenquelle übermittelte ID, unabhängig davon, ob für diese ID ein {ref}`Mapping <h-datasources-general-mapping>` eingerichtet ist.
```
