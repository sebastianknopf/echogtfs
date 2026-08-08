# SIRI-SX

Die SIRI-SX-Datenquelle wird verwendet, um Daten aus einem SIRI-SX-Feed in EchoGTFS zu übernehmen. Sie eignet sich besonders für die Synchronisation von Meldungen und anderen betriebsbezogenen Informationen aus externen Fahrplandatenquellen. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue oder aktualisierte Meldungen automatisch im System verfügbar werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein SIRI-SX-Endpunkt benötigt, der die Daten im SIRI-Format bereitstellt. In der Konfiguration können Sie festlegen, welcher Endpoint verwendet werden soll, welche Filterkriterien für die Verarbeitung genutzt werden und wie der Import mit Sonderbehandlungen bei Haltestellen verhalten soll.

Die Datenquelle verarbeitet die eingehenden Meldungen automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter können in der Konfiguration der Datenquelle gesetzt werden:

- **Endpunkt**: Die URL des SIRI-SX-Endpoints, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Meldungen.
- **Token**: Optionales Zugriffstoken für geschützte Endpunkte.
  - Ergebnis: Wenn ein Token hinterlegt ist, wird er bei der Anfrage mitgesendet.
- **Dialekt**: Die zu verwendende SIRI-SX-Implementierungsvariante.
- **Filter**: Optionaler Filter für Betreiberkennungen.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Meldungen aus den angegebenen Betreiberreferenzen berücksichtigt.

## Verfügbare Dialekte

Die SIRI-SX-Datenquelle verwendet die folgenden Dialekte:

- **SIRI-SX**
- **SIRI-SX Swiss**
