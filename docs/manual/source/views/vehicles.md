# Fahrzeuge

Im Bereich "Fahrzeuge" werden alle aktuellen Fahrzeugpositionen angezeigt.

```{figure} ../_static/images/vehicles-overview-screen.png
:name: img-vehicles-overview-screen
```

- Der "Schnellfilter" ermöglicht die Suche nach Fahrzeugen anhand ihrer Bezeichnung oder der zugeorneten Linie oder Fahrt
- Über den "Filter" lassen sich die Meldungen wie folgt filtern:
    - **aktive Fahrzeuge**: Es werden alle aktivierten Fahrzeuge mit einbezogen
    - **inaktive Fahrzeuge**: Es werden alle deaktivierten Fahrzeuge mit einbezogen
- Durch Klick auf ein Fahrzeug-Icon werden die Details zu dem Fahrzeug angezeigt:
    - **Aktualisiert**: Letzter Aktualisierungszeitpunkt der Fahrzeugposition, welcher vom Fahrzeug gemeldet wurde
    - **Linie**: Linie, auf der das Fahrzeug aktuell verkehrt. Wenn keiner Linie zugeordnet werden konnte, wird dies über ein Fehler-Icon kenntlich gemacht
    - **Fahrt-ID**: Zugeordnete Fahrt, auf der das Fahrzeug aktuell verkehrt. Wenn die Fahrt nicht aus dem Soll-Fahrplan ermittelt werden konnte, wird dies über ein Fehler-Icon kenntlich gemacht
    - **Zuordnungstyp**: Gibt an, auf welchem Weg eine Fahrt aus der Datenquelle einer konkreten Fahrt im Soll-Fahrplan zugeordnet wurde. Folgende Werte können hier auftauchen:
        - `DIRECT_BY_ID`: die Fahrt wurde anhand ihrer ID im Soll-Fahrplan gefunden
        - `MATCHED_BY_CACHED_ID`: die Fahrt wurde bereits durch eine andere Datenquelle einer Fahrt im Soll-Fahrplan zugeordnet
        - `MATCHED_BY_START_STOP`: die Fahrt wurde anhand ihrer Start- und Endhaltestelle, sowie der Abfahrts- und Ankunftszeit im Soll-Fahrplan gefunden
        - `MATCHED_BY_CURRENT_STOP`: die Fahrt wurde anhand von mindestens einem Unterwegshalt im Soll-Fahrplan gefunden
        - `NO_MATCH_GENERAL`: es wurde keine passende Fahrt im Soll-Fahrplan gefunden
        - `NO_MATCH_AMBIGUOUS_TRIP`: es wurde keine _eindeutig passende Fahrt_ im Soll-Fahrplan gefunden
    - **Aktueller Halt**: Aktuelle bzw. nächste Haltestelle, die das Fahrzeug anfährt. Wenn die Haltestelle nicht aus dem Soll-Fahrplan ermittelt werden konnte, wird dies über ein Fehler-Icon kenntlich gemacht
    - **Haltstatus**: Angabe über den Bezug zur aktuellen Haltestelle. Mögliche Werte sind:
        - `INCOMING_AT`: Das Fahrzeug erreicht die aktuelle Haltestelle
        - `STOPPED_AT`: Das Fahrzeug steht an der aktuellen Haltestelle
        - `IN_TRANSIT_TO`: Das Fahrzeug befindet sich im Zulauf auf die aktuelle Haltestelle
