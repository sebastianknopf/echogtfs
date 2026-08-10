# SIRI-SX

Die SIRI-SX-Datenquelle wird verwendet, um Daten aus einem SIRI-SX-Feed in EchoGTFS zu übernehmen. Sie eignet sich besonders für die Synchronisation von Meldungen und anderen betriebsbezogenen Informationen aus externen Fahrplandatenquellen. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue oder aktualisierte Meldungen automatisch im System verfügbar werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein SIRI-SX-Endpunkt benötigt, der die Daten im SIRI-Format bereitstellt. In der Konfiguration können Sie festlegen, welcher Endpoint verwendet werden soll und welche Filterkriterien für die Verarbeitung genutzt werden.

Die Datenquelle verarbeitet die eingehenden Meldungen automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter können in der Konfiguration der Datenquelle gesetzt werden:

- **Endpunkt**: Die URL des SIRI-SX-Endpoints, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Meldungen.
- **Leitstellenkennung**: Die vereinbarte Leitstellenkennung des anfragenden Systems.
  - Ergebnis: Diese Angabe wird in die Anfrage übernommen und hilft, die Anforderung eindeutig zuzuordnen.
- **Methode**: Auswahl zwischen "request/response" und "publish/subscribe".
  - Ergebnis: Derzeit wird "request/response" unterstützt. "publish/subscribe" ist noch nicht verfügbar.
- **Dialekt**: Die zu verwendende SIRI-SX-Implementierungsvariante.
- **Filter**: Optionaler Filter für Betreiberkennungen.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Meldungen aus passenden Betreiberreferenzen berücksichtigt. `*` wird als Wildcard behandelt und steht für beliebig viele beliebige Zeichen.

## Verfügbare Dialekte

Die SIRI-SX-Datenquelle verwendet die folgenden Dialekte:

- **SIRI-SX**
- **SIRI-SX Swiss**
