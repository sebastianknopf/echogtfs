# SIRI-VM

Die SIRI-VM-Datenquelle wird verwendet, um Fahrzeugpositionen aus einem SIRI-VM-Feed in EchoGTFS zu importieren. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue oder aktualisierte Meldungen automatisch im System verfügbar werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein SIRI-SX-Endpunkt benötigt, der die Daten im SIRI-Format bereitstellt. In der Konfiguration können Sie festlegen, welcher Endpoint verwendet werden soll und welche Filterkriterien für die Verarbeitung genutzt werden.

Die Datenquelle verarbeitet die eingehenden Fahrzeugpositionen automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter kannst du in der Konfiguration der Datenquelle setzen:

- **Endpoint URL**: URL des SIRI-VM-Endpunkts.
  - Ergebnis: Beim Ausführen wird diese URL per HTTP-POST abgefragt.
- **Participant Reference**: Leitstellenkennung für die Anfrage.
  - Ergebnis: Der Wert wird in der SIRI-Anfrage als Requestor Ref verwendet und kann zusätzlich per Platzhalter im Endpunkt genutzt werden.
- **Methode**: Auswahl zwischen "request/response" und "publish/subscribe".
  - Ergebnis: Derzeit wird "request/response" unterstützt. "publish/subscribe" ist noch nicht verfügbar.
- **Dialekt**: Die zu verwendende SIRI-VM-Implementierungsvariante.
- **Filter**: Optionaler Filter für Betreiberkennungen.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Fahrzeugpositionen aus den angegebenen Betreiberreferenzen berücksichtigt.

## Verfügbare Dialekte

Die SIRI-VM-Datenquelle verwendet aktuell den folgenden Dialekt:

- **SIRI-VM**
