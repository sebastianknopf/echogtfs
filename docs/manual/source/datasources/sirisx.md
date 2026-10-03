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
- **Filter**: Optionaler Filter für Teilnehmerkennungen und Linien.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Meldungen mit passenden Teilnehmerkennungen oder mindestens einem Bezug zu einer Linie berücksichtigt.

Generelle Hinweise zur Verwendung von Filtern sind in der {ref}`Datenquellenübersicht <h-datasources-filters>` beschrieben.

## Verfügbare Dialekte

Die SIRI-SX-Datenquelle verwendet die folgenden Dialekte:

- **SIRI-SX**
- **SIRI-SX Swiss**

(h-datasources-sirisx-closing-alerts)=

### Behandlung von Endmeldungen

Wenn eine Meldung mit `Progress=closing` wird von den Dialekten folgendermaßen verarbeitet:

- Die Auswirkung wird fest auf `UNKNOWN_EFFECT` gesetzt. Dies hat zur Folge, dass die Meldung nach wie vor angezeigt wird und aktiv ist, aber basierend auf der Auswirkung beispielsweise keine Fahrt- oder Haltausfälle mehr implizit erzeugt werden. _Anreicherungen mit Bezug auf die Auswirkungen greifen in diesem Fall nicht mehr!_
- Der jeweils letzte Gültigkeits- und Veröffentlichungszeitraum wird gespeichert und die "Gültig Bis" Information entfernt. Dadurch bleibt die Endmeldung solange bestehen bis sie durch die Datenquelle oder die Datenbereinigung gelöscht wird.
