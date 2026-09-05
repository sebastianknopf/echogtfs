(h-monitoring-api-monitoring-api)=

# Monitoring API

Um EchoGTFS auch mit externen Tools überwachen zu können und Rückschlüsse auf die Datenverfügbarkeit- und Qualität ziehen zu können, bietet EchoGTFS eine dokumentierte und stabile Monitoring-Schnittstelle als JSON-basierte REST-API an. 

## Funktionsumfang

Die Monitoring-API bietet stets Zugriff auf den **aktuellen Systemzustand**.

Die Monitoring-API bietet drei wichtige Endpunkte:

- `/api/monitoring/system`: Aktuell aktive Datenquellen und im Soll-Fahrplan importierte Linien zum Filtern der nachfolgenden beiden Endpunkte
- `/api/monitoring/statistics`: Aktuelle KPIs bzw. Daten zur Berechnung von KPIs über den aktuellen Systemzustand
- `/api/monitoring/conflicts`: Aktuell anliegende und erkannte Konflikte in den enthaltenen Daten

## Restriktionen

Die Monitoring-API bringt folgende Restriktionen mit:

- Es werden grundsätzlich keine historischen Zustände erhoben und ausgegeben. Die Monitoring-API bietet immer nur Zugriff auf den aktuellen Systemzustand.
- Ob bestimmte Konflikte erkannt werden, hängt maßgeblich von den Einstellungen der Datenquellen ab:
    - Wird beispielsweise eine Datenquelle mit der Verfahrensweise "ungültige Bezüge verwerfen" angelegt, werden ungültige Objekte oder Referenzen vollständig verworfen und tauchen entsprechend auch nicht als Konflikt auf.
- Fehler in den Rohdaten werden derzeit nicht gesondert überwacht, ggf. werden Datenobjekte verworfen.

## Technische Hinweise

### Authentifizierung

Der Zugriff auf die Monitoring-API ist nur mit Authentifizierung notwendig. Hierzu muss vorher in {ref}`h-accounts-accounts` ein User mit mindestens dem Recht "Poweruser" angelegt werden. Über diesen User kann dann die Authentifizierung erfolgen. Es wird dringend empfohlen für die Monitoring-API einen dedizierten User anzulegen, der bei Bedarf ohne Auswirkungen auf andere Accounts deaktiviert werden kann.

Das entsprechend beim Login über den Login-Endpunkt erhaltene Token muss bei allen Requests über den Header `Authorization` mit dem Wert `Bearer {TOKEN}` mitgeschickt werden. Um das Token ohne neues Login erneuern zu können, liefern alle Antworten an die Monitoring-API den Header `X-New-Token` mit. In diesem Header befindet sich ein periodisch aktualisiertes Token, mit dem die Authentifizierung wahlweise nach Ablauf des initialen Tokens oder direkt beim nächsten Request erfolgen kann.

### Swagger

Die Monitoring-API ist auch als OpenAPI-Spezifikation und Swagger-UI verfügbar. Hierzu muss in den Umgebungsvariablen von EchoGTFS die Variable `DOCS_ENABLED` auf `true` gesetzt werden. Anschließend ist die Swagger-UI unter `/api/swagger` erreichbar und kann auch für einfache Tests genutzt werden.

```{warning}
Die Swagger-UI sollte in Produktivumgebungen immer deaktiviert sein, um Sicherheitsrisiken zu minimieren.
```