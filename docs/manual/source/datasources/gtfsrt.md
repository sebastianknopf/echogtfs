# GTFS-RT

Die GTFS-RT-Datenquelle wird verwendet, um Echtzeitdaten aus einem GTFS-Realtime-Feed in EchoGTFS zu übernehmen. Sie eignet sich für die Synchronisation von Service Alerts, Trip Updates und Vehicle Positions. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue oder geänderte Echtzeitdaten automatisch im System verfügbar werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein GTFS-Realtime-Endpunkt benötigt, der die Daten im Protobuf-Format bereitstellt. In der Konfiguration können Sie festlegen, welcher Endpoint verwendet werden soll und welche Art von Echtzeitdaten importiert werden soll.

Die Datenquelle verarbeitet die eingehenden Echtzeitdaten automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter können in der Konfiguration der Datenquelle gesetzt werden:

- **Endpunkt**: Die URL des GTFS-Realtime-Endpoints, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Echtzeitdaten.
- **Feed-Typ**: Die Art der zu importierenden Daten.
  - Ergebnis: Je nach Auswahl werden Service Alerts, Trip Updates oder Fahrzeugpositionen verarbeitet.
- **Token**: Optionales Zugriffstoken für geschützte Endpunkte.
  - Ergebnis: Wenn ein Token hinterlegt ist, wird er bei der Anfrage mitgesendet.

## Verfügbare Dialekte

Die GTFS-RT-Datenquelle verwendet die folgenden Dialekte:

- **GTFS-RT ServiceAlerts**
