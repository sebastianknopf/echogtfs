# SIRI-ET

Die SIRI-ET-Datenquelle wird verwendet, um Fahrteninformationen aus einem SIRI-ET-Feed in EchoGTFS zu übernehmen. Sie eignet sich insbesondere für die Synchronisation von geplanten, zusätzlichen oder ausgefallenen Fahrten. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue oder geänderte Fahrten automatisch in das System übernommen werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein SIRI-ET-Endpunkt benötigt, der die Daten im SIRI-Format bereitstellt. In der Konfiguration können Sie festlegen, welcher Endpoint verwendet werden soll, welche Leitstellenkennung für die Anfrage genutzt wird und wie der Import mit Filtern oder Sonderbehandlungen bei Haltestellen verhalten soll.

Die Datenquelle verarbeitet die eingehenden Fahrtdaten automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter können in der Konfiguration der Datenquelle gesetzt werden:

- **Endpunkt**: Die URL des SIRI-ET-Endpoints, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Fahrtdaten.
- **Leitstellenkennung**: Die vereinbarte Leitstellenkennung des anfragenden Systems.
  - Ergebnis: Diese Angabe wird in die Anfrage übernommen und hilft, die Anforderung eindeutig zuzuordnen.
- **Methode**: Auswahl zwischen "request/response" und "publish/subscribe".
  - Ergebnis: Derzeit wird "request/response" unterstützt. "publish/subscribe" ist noch nicht verfügbar.
- **Dialekt**: Die zu verwendente SIRI-ET Implementierungsvariante.
- **Ungeplante Halte als Zusatzhalte behandeln**: Aktiviert die Behandlung von unerwarteten Halten als zusätzliche Halte.
  - Ergebnis: Solche Halte werden im Importverlauf wie Zusatzhalte behandelt. Wenn die Option deaktiviert ist, werden unerwartete Halte in den Eingangsdaten verworfen.
- **Fehlende Halte als ausgefallene Halte behandeln**: Aktiviert die Behandlung fehlender Halte als ausgefallene Halte.
  - Ergebnis: Fehlende Halte werden im Importverlauf wie ausgefallene Halte behandelt. Wenn die Option deaktiviert ist, werden fehlende Halte in den Eingangsdaten ignoriert.
- **Filter**: Optionaler Filter für Betreiberkennungen.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Fahrten aus passenden Betreiberreferenzen berücksichtigt. `*` wird als Wildcard behandelt und steht für beliebig viele beliebige Zeichen.

## Verfügbare Dialekte

Die SIRI-ET-Datenquelle verwendet den folgenden Dialekte:

- **SIRI-ET** (Standard)
