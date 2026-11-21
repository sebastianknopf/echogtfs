# EFA-JSON

Die EFA-JSON Datenquelle (EFA = Elektronische Fahrplanauskunft der Fa. Mentz) wird verwendet, um Echtzeitdaten von einem EFA-Server in EchoGTFS zu übernehmen. Sie eignet sich besonders zur Synchronisation von ServiceAlerts. Nach der Einrichtung kann die Datenquelle zeit- und eventgesteuert ausgeführt werden, sodass neue oder geänderte Echtzeitdaten automatisch im System verfügbar werden.

## Verwendung

Für die Verwendung der Datenquelle wird ein EFA-Server mit aktivierter EFA-JSON API benötigt. In der Konfiguration können die anzufragende URL inklusive eventueller Query-Parameter festgelegt werden. Außerdem kann eine Sprache eingestellt werden, in der die Daten für die ServiceAlerts importiert werden.

## Parameter

Die folgenden Parameter können in der Konfiguration der Datenquelle gesetzt werden:

- **Endpunkt**: Die URL des EFA-Servers, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Echtzeitdaten.
- **Dialekt**: Die Art des Requests an den EFA-Server.
  - Ergebnis: Je nach Auswahl werden Meldungen, Echtzeitdaten oder Fahrzeugpositionen verarbeitet.
- **Sprache**: Sprache, in der die Daten vom EFA-Server geliefert werden.
  - Ergebnis: Bei textbehafteten Daten werden diese mit der eingestellten Sprache importiert.
- **Filter**: Optionaler Filter für Linien und Betreiber.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Meldungen mit mindestens einem passenden Bezug zu einer Linie bzw. zu einem Betreiber berücksichtigt. 
      - Die Filter der Filterklasse `line` greifen auf die Liniekennung.
      - Die Filter der Filterklasse `operator` greifen auf den ProviderCode und OperatorRef.

Generelle Hinweise zur Verwendung von Filtern sind in der {ref}`Datenquellenübersicht <h-datasources-filters>` beschrieben.

## Verfügbare Ausführungsarten

Die EFA-JSON Datenquelle unterstützt folgende Ausführungsarten:

- Zeitbasiert
- Eventbasiert

## Verfügbare Dialekte

Die EFA-JSON Datenquelle verwendet die folgenden Dialekte:

- **ADDINFO**: Import von ServiceAlerts über den `ADDINFO`-Request.
