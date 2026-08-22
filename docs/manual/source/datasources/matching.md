# Matching

Das Matching ordnet externe Fahrten-IDs aus Datenquellen den passenden Fahrten aus Ihrem GTFS-Feed zu. Dadurch können Fahrten und Fahrzeugpositionen auch dann korrekt verarbeitet werden, wenn die Quell-ID nicht direkt zur GTFS-ID passt.

## Einsatzbereiche

Matching wird nur dann angewendet, wenn eine eingehende Fahrt nicht direkt über ihre Fahrt-ID im GTFS-Feed gefunden wird.

Wenn eine direkte Zuordnung möglich ist, wird kein Matching benötigt.

## Ablauf des Matchings

Die Zuordnung erfolgt schrittweise:

1. Vorhandene Zuordnung aus einem früheren Lauf wiederverwenden.
2. Abgleich über Linie, Betriebstag sowie geplante Start-/Endzeit und Start-/Endhaltestelle.
3. Fallback-Abgleich über drei zufällig gewählte Zwischenhalte.

Sobald eine Stufe genau eine eindeutige Fahrt liefert, wird diese verwendet.

## Regeln für Eindeutigkeit

Eine Zuordnung wird nur übernommen, wenn genau eine passende GTFS-Fahrt gefunden wird.

- Kein Treffer: Es erfolgt keine Zuordnung.
- Mehrdeutiger Treffer: Es erfolgt ebenfalls keine Zuordnung.

## Zeitfenster bei Zeitabgleichen

Bei Zeitvergleichen um die Start- und Endzeit einer Fahrt gilt eine Toleranz von 60 Sekunden um die geplante Zeit. Beim Matching anhand von zufälligen Zwischenhalten gilt eine Toleranz von 120 Sekunden um die geplante Zeit.

Dadurch bleiben kleine Abweichungen zwischen Quelle und GTFS-Feed unkritisch.

## Verwendung globaler Haltestellen-IDs

Bei Verwendung von globalen Haltestellen-IDs werden diese auf Haltestellen-Level heruntergebrochen und berücksichtigt. So wird beispielsweise bei der globalen ID `de:08321:11:0:1` in den Quell-Daten nur der Anteil `de:08231:11` verwendet.

Dadurch führen beispielsweise falsch versorgte Steige in den Quelldaten nicht zwangsläufig zu einem fehlgeschlagenen Match.

## Fallback über Zwischenhalte

Der Zwischenhalt-Fallback wird automatisch verwendet, wenn aus Start- und Endzeit einer Fahrt kein erfolgreiches Match gefunden wurde.

In diesem Fall werden maximal 3 zufällig gewählte Zwischenhalte (Haltestelle + Zeit) mit den GTFS-Haltezeiten verglichen:

- Die Haltestelle muss zur Fahrt passen.
- Die Zeit muss innerhalb einer 120-Sekunden-Toleranz um die geplante Abfahrtszeit liegen.
- Alle angegebenen Zwischenhalte müssen zur gleichen Fahrt passen.

## Auswirkungen auf den Betrieb

Wenn kein eindeutiges Matching möglich ist, bleibt der Fahrtbezug unaufgelöst. Welche Folge das hat, hängt von der in der Datenquelle eingestellten Verfahrensweise bei ungültigen Bezügen ab.

Informationen dazu finden Sie unter {ref}`h-datasources-invalid-reference-policies`.

## Empfehlungen

1. Pflegen Sie Mapping-Einträge für Haltestellen und Linien sorgfältig.
2. Stellen Sie sicher, dass geplante Zeiten aus der Quelle konsistent sind.
3. Prüfen Sie bei häufigen Nicht-Treffern die Request-Logs der Datenquelle.
