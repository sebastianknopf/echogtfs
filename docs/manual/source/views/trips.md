# Fahrten

Im Bereich "Fahrten" werden alle aktuellen Fahrten angezeigt.

```{figure} ../_static/images/trips-overview-screen.png
:name: img-trips-overview-screen
```

- Im oberen Bereich besteht die Möglichkeit, die Fahrten nach Datum zu sortieren:
    - **nach Start aufsteigend**: Zeigt die Fahrten nach ihrer Startzeit aufsteigend sortiert an
    - **nach Start absteigend**: Zeigt die Fahrten nach ihrer Startzeit absteigend sortiert an
- Der "Schnellfilter" ermöglicht die Suche nach Fahrten anhand ihrer Fahrt-ID, der Start- oder Endhaltestelle oder der zugeorneten Linie oder Fahrt
- Über den "Filter" lassen sich die Meldungen wie folgt filtern:
    - **aktive Fahrten**: Es werden alle aktivierten Fahrten mit einbezogen
    - **inaktive Fahrten**: Es werden alle deaktivierten Fahrten mit einbezogen
- Für jede Fahrt werden in der Übersicht folgende Informationen angezeigt:
    - **Linie**: Linie, zu der die entsprechende Fahrt zugeordnet ist
    - **Fahrt-ID**: Fahrt-ID, zu der die entsprechende Fahrt zugeordnet ist
    - **Betriebstag, Start- und Ende**: Betriebstag, Startzeit- und Haltestelle, Ankunftszeit- und Haltestelle, die von der Datenquelle gemeldet wurde
    - **Status**: Status (planmäßig, Zusatzfahrt, Fahrtausfall) der Fahrt
    - **Datenquelle**: Name der Datenquelle von der eine Fahrt synchronisiert wurde
    - **Aktivierungsstatus**: Information, wenn eine Fahrt deaktiviert wurde. Deaktivierte Fahrten werden in der GTFS-RT Ausgabe unterdrückt. Über den "On/Off" Button können Fahrten aktiviert oder deaktiviert werden.
    - **Fehlerstatus**: Rotes Warndreieck, wenn eine Fahrt ungültige Bezüge (insb. Linie und Haltestelle) aufweist. Solange die Fahrt nicht deaktiviert ist, wird sie weiterhin über GTFS-RT ausgegeben und kann dadurch zu Fehlern bei Abnehmersystemen führen

Um die Details zu einer Fahrt anzuzeigen, klicken Sie auf den "View" Button in der entsprechenden Zeile. Daraufhin wird folgender Dialog gezeigt, in dem alle wichtigen Informationen rund um die Fahrt zu sehen sind:

```{figure} ../_static/images/trips-detail-screen.png
:name: img-trips-detail-screen
```

- Im oberen Bereich des Dialogs werden alle Basisdaten wie **Fahrt-ID**, **Linie**, **Originäre Fahrt-ID**, **Betriebstag, Fahrtstart und -Ende**, sowie **Status** der Fahrt angezeigt. Die Fahrt-ID ist die ID, mit der die Fahrt im GTFS-RT publiziert wird und die zum Soll-Fahrplan passt. Die originäre Fahrt-ID ist die ID, mit der die Fahrt aus der Datenquelle synchronisiert wurde.
- Im unteren Bereich werden die einzelnen Haltestellen der Fahrt mit **Ankunftszeit**, **Abfahrtszeit**, **Status** und **Zuordnungstyp** angezeigt. Der Zuordnungstyp gibt an, auf welchem Weg eine Fahrt aus der Datenquelle einer konkreten Fahrt im Sollfahrplan zugeordnet wurde. Folgende Werte können hier auftauchen:
    - `DIRECT_BY_ID`: die Fahrt wurde anhand ihrer ID im Soll-Fahrplan gefunden
    - `MATCHED_BY_START_STOP`: die Fahrt wurde anhand ihrer Start- und Endhaltestelle, sowie der Abfahrts- und Ankunftszeit im Soll-Fahrplan gefunden
    - `MATCHED_BY_CURRENT_STOP`: die Fahrt wurde anhand von mindestens einem Unterwegshalt im Soll-Fahrplan gefunden
    - `NO_MATCH_GENERAL`: es wurde keine passende Fahrt im Soll-Fahrplan gefunden
    - `NO_MATCH_AMBIGUOUS_TRIP`: es wurde keine _eindeutig passende Fahrt_ im Soll-Fahrplan gefunden
- Wenn eine **Linie oder Trip-ID nicht über die GTFS-Daten** gefunden wurde, werden mit einem roten Ausrufezeichen gekennzeichnet. In diesem Fall wird jeweils die originale Linien- und Fahrt-ID angezeigt, welche aus der Datenquelle der Fahrt übermittelt wurde