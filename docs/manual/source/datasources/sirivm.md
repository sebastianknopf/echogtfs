# SIRI-VM

Die SIRI-VM-Datenquelle wird verwendet, um Fahrzeugpositionen aus einem SIRI-VM-Feed in EchoGTFS zu importieren. Nach der Einrichtung kann die Datenquelle regelmäßig ausgeführt werden, sodass neue oder aktualisierte Meldungen automatisch im System verfügbar werden.

## Verwendung

Für die Nutzung der Datenquelle wird ein SIRI-SX-Endpunkt benötigt, der die Daten im SIRI-Format bereitstellt. In der Konfiguration können Sie festlegen, welcher Endpoint verwendet werden soll und welche Filterkriterien für die Verarbeitung genutzt werden.

Die Datenquelle verarbeitet die eingehenden Fahrzeugpositionen automatisch und stellt sie für die weitere Nutzung in EchoGTFS bereit.

## Parameter

Die folgenden Parameter kannst du in der Konfiguration der Datenquelle setzen:

- **Endpunkt**: Die URL des SIRI-VM-Endpoints, von dem die Daten abgerufen werden.
  - Ergebnis: Die Datenquelle fragt diesen Endpunkt beim Ausführen ab und verarbeitet die gelieferten Meldungen.
- **Consumer-Endpunkt**: Optionale URL, unter der ein Consumer für abonnementbasierte Datenquellen erreichbar ist.
- **Participant Reference**: Leitstellenkennung für die Anfrage.
  - Ergebnis: Der Wert wird in der SIRI-Anfrage als Requestor Ref verwendet und kann zusätzlich per Platzhalter im Endpunkt genutzt werden.

- **Dialekt**: Die zu verwendende SIRI-VM-Implementierungsvariante.
- **Filter**: Optionaler Filter für Betreiberkennungen und Linien.
  - Ergebnis: Wenn ein Filter gesetzt ist, werden nur Fahrzeugpositionen mit passenden Betreiberreferenzen oder Linien berücksichtigt.

Generelle Hinweise zur Verwendung von Filtern sind in der {ref}`Datenquellenübersicht <h-datasources-filters>` beschrieben.

## Verfügbare Ausführungsarten

Die SIRI-VM-Datenquelle unterstützt folgende Ausführungsarten:

- Zeitbasiert
- Eventbasiert
- Abobasiert

```{note}
In der abobasierten Ausführung unterstützt die SIRI-VM-Datenquelle derzeit nur den Betriebsmodus `DirectDelivery`! Der Betriebsmodus `FetchedDelivery` ist aktuell noch nicht implementiert.
```

## Verfügbare Dialekte

Die SIRI-VM-Datenquelle verwendet aktuell den folgenden Dialekt:

- **SIRI-VM**
