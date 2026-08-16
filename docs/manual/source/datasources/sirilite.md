# SIRI-Lite

Die SIRI-Lite-Datenquelle wird verwendet, um Daten aus einem SIRI-Lite-Feed in EchoGTFS zu übernehmen. SIRI-Lite ist eine Ausprägung des SIRI-Standards, bei dem die Daten nicht wie übliche über HTTP-POST-Requests mit Leitstellenkennung übermittelt, sondern einfach als HTTP-GET-Request heruntergeladen werden. Die genaue Umsetzung hängt stark vom Datenanbieter ab. Sie dient als gemeinsame Schnittstelle für verschiedene SIRI-Varianten und kann je nach Konfiguration ServiceAlerts (SIRI-SX), TripUpdates (SIRI-ET) oder VehiclePositions (SIRI-VM) verarbeiten. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue Informationen automatisch übernommen werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein SIRI-Lite-Endpunkt benötigt, der die Daten im SIRI-Format bereitstellt. In der Konfiguration können Sie festlegen, welche Variante verwendet werden soll, welche Filterkriterien greifen und wie der Import bei Sonderfällen rund um Halte behandelt werden soll.

Die Datenquelle verarbeitet die eingehenden Daten automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter können in der Konfiguration der Datenquelle gesetzt werden:

- **Endpunkt**: Die URL des SIRI-Lite-Endpoints, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Daten.
- **Token**: Optionales Zugriffstoken für geschützte Endpunkte.
  - Ergebnis: Wenn ein Token hinterlegt ist, wird er bei der Anfrage mitgesendet.
- **Dialekt**: Die zu verwendende SIRI-Implementierungsvariante.
- **Ungeplante Halte als Zusatzhalte behandeln**: _(nur wirksam bei SIRI-ET!)_ Aktiviert die Behandlung von unerwarteten Halten als zusätzliche Halte.
  - Ergebnis: Solche Halte werden im Importverlauf wie Zusatzhalte behandelt. Wenn die Option deaktiviert ist, werden unerwartete Halte in den Eingangsdaten verworfen.
- **Fehlende Halte als ausgefallene Halte behandeln**:  _(nur wirksam bei SIRI-ET!)_ Aktiviert die Behandlung fehlender Halte als ausgefallene Halte.
  - Ergebnis: Fehlende Halte werden im Importverlauf wie ausgefallene Halte behandelt. Wenn die Option deaktiviert ist, werden fehlende Halte in den Eingangsdaten ignoriert.
- **Filter**: Optionaler Filter für Betreiberkennungen.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur passende Betreibergruppen berücksichtigt. `*` wird als Wildcard behandelt und steht für beliebig viele beliebige Zeichen.

```{warning}
In der aktuellen Umsetzungsvariante wird die Ausgabe von Zusatzhalten über GTFS-RT nicht unterstützt! Die hierzu notwendige [Erweiterung mit `TripModifications`](https://gtfs.org/documentation/realtime/reference/#message-tripmodifications) ist aktuell noch experimentell und [wird von GoogleTransit noch nicht unterstützt](https://developers.google.com/transit/gtfs-realtime/reference?hl=de).
```

## Verfügbare Dialekte

Die SIRI-Lite-Datenquelle verwendet die folgenden Dialekte:

- **SIRI-SX**
- **SIRI-SX Swiss**
- **SIRI-ET**
