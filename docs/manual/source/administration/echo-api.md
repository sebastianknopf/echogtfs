(h-echo-api-echo-api)=

# Echo API

Um EchoGTFS mit externen Tools und Erweiterungen überwachen und steuern zu können, bietet EchoGTFS eine dokumentierte und stabile Schnittstelle als JSON-basierte REST-API an. 

## Funktionsumfang

Die Echo-API bietet stets Zugriff auf den **aktuellen Systemzustand** über folgende Endpunkte:

- `GET /api/monitoring/system`: Aktuell aktive Datenquellen und im Soll-Fahrplan importierte Linien zum Filtern der nachfolgenden beiden Endpunkte
- `GET /api/monitoring/statistics`: Aktuelle KPIs bzw. Daten zur Berechnung von KPIs über den aktuellen Systemzustand
- `GET /api/monitoring/conflicts`: Aktuell anliegende und erkannte Konflikte in den enthaltenen Daten
- `POST /api/push/{data_source_id}`: Eventbasierte Ausführung von entsprechend Konfigurierten Datenquellen

## Restriktionen

Die Echo-API bringt folgende Restriktionen mit:

- Es werden grundsätzlich keine historischen Zustände erhoben und ausgegeben. Die Echo-API bietet immer nur Zugriff auf den aktuellen Systemzustand.
- Ob bestimmte Konflikte erkannt werden, hängt maßgeblich von den Einstellungen der Datenquellen ab:
    - Wird beispielsweise eine Datenquelle mit der Verfahrensweise "ungültige Bezüge verwerfen" angelegt, werden ungültige Objekte oder Referenzen vollständig verworfen und tauchen entsprechend auch nicht als Konflikt auf.
- Fehler in den Rohdaten werden derzeit nicht gesondert überwacht, ggf. werden Datenobjekte verworfen.
- Die eventbasierte Ausführung von Datenquellen ist nur für entsprechend konfigurierte Datenquellen möglich. Der Payload wird dabei im Body des POST-Requests übergeben. Außerdem muss in den Einstellungen die Push-API aktiviert sein.
- Bei der eventbasierten Ausführung von Datenquellen kann jede Datenquelle immer nur einmal gleichzeitig ausgeführt werden. Dadurch werden Interferenzen zwischen mehreren parallelen Durchläufen vermieden.

## Technische Hinweise

### Authentifizierung

Der Zugriff auf die Echo-API ist nur mit Authentifizierung notwendig. Hierzu muss vorher in {ref}`h-accounts-accounts` ein User mit dem Recht "API" angelegt werden. Über diesen User kann dann die Authentifizierung erfolgen. Es wird dringend empfohlen für die Echo-API einen dedizierten User anzulegen, der bei Bedarf ohne Auswirkungen auf andere Accounts deaktiviert werden kann.

Das entsprechend beim Login über den Login-Endpunkt erhaltene Token muss bei allen Requests über den Header `Authorization` mit dem Wert `Bearer {TOKEN}` mitgeschickt werden. Um das Token ohne neues Login erneuern zu können, liefern alle Antworten an die Echo-API den Header `X-New-Token` mit. In diesem Header befindet sich ein periodisch aktualisiertes Token, mit dem die Authentifizierung wahlweise nach Ablauf des initialen Tokens oder direkt beim nächsten Request erfolgen kann.

### Swagger

Die Echo-API ist auch als OpenAPI-Spezifikation und Swagger-UI verfügbar. Hierzu muss in den Umgebungsvariablen von EchoGTFS die Variable `DOCS_ENABLED` auf `true` gesetzt werden. Anschließend ist die Swagger-UI unter `/api/swagger` erreichbar und kann auch für einfache Tests genutzt werden.

```{warning}
Die Swagger-UI sollte in Produktivumgebungen immer deaktiviert sein, um Sicherheitsrisiken zu minimieren.
```