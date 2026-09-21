(h-push-api-push-api)=

# Push API

Um Daten aus externen Systemen echtzeitnah in EchoGTFS importieren zu können, besteht die Möglichkeit, eventbasierte Datenquellen über die Push-API anzusprechen. 

Die Push-API ist per default deaktiviert und muss in den Systemeinstellungen unter {ref}`h-system-settings-push-api` gesondert aktiviert werden.

## Funktionsumfang

Die Push-API ermöglicht das eventbasierte Ausführen einer Datenquelle. Dazu wird der dem Request der Payload übergeben, der anschließend von der Datenquelle verarbeitet werden soll. Die Datenquelle wird beim Aufruf synchron ausgeführt und das Ergebnis direkt an die aufrufende Instanz zurückgegeben.

Die Push-API bietet folgende Endpunkte:

- `POST /api/push/datasource/{dataSourceId}`: Ausführung der Datenquelle mit dem übergebenen Payload

Die ID der Datenquelle kann in der Übersicht für Datenquellen ermittelt werden.

## Restriktionen

Bei der Ausführung von Datenquellen über die Push-API kann jede Datenquelle immer nur einmal gleichzeitig ausgeführt werden. Dadurch werden Interferenzen zwischen mehreren parallelen Durchläufen vermieden.

## Technische Hinweise

### Authentifizierung

Für den Zugriff auf die Push-API werden in den Systemeinstellungen optional BasicAuth Zugangsdaten hinterlegt. Die Authentifizierung über einen regulären EchoGTFS User wird aktuell nicht unterstützt.

### Swagger

Die Push-API ist auch als OpenAPI-Spezifikation und Swagger-UI verfügbar. Hierzu muss in den Umgebungsvariablen von EchoGTFS die Variable `DOCS_ENABLED` auf `true` gesetzt werden. Anschließend ist die Swagger-UI unter `/api/swagger` erreichbar und kann auch für einfache Tests genutzt werden.

```{warning}
Die Swagger-UI sollte in Produktivumgebungen immer deaktiviert sein, um Sicherheitsrisiken zu minimieren.
```