# Grundsätzliches

Datenquellen ermöglichen die Anbindung externer Systeme (ITCS, Datendrehscheiben, Auskunftssysteme) um Daten von diesen Quellen zu synchronisieren.

```{note}
Fahrten und Fahrzeugspositionen können derzeit ausschließlich über Datenquellen in EchoGTFS synchronisiert werden. Die manuelle Eingabe ist diese Daten nicht möglich.
```

Um Datenquellen zu verwalten, wechseln Sie in den Bereich "Datenquellen" im Seitenmenü. Dort sehen Sie eine Übersicht über alle bisher eingerichteten Datenquellen:

```{figure} ../_static/images/datasources-overview-screen.png
:name: img-datasources-overview-screen
```

- Über den "Play"-Button kann die Datenquelle **sofort ausgeführt** werden
- Über den "Log"-Button lassen sich die **Request-Logs der letzten 24 Stunden** angezeigt werden
- Über den "Edit"-Button können **bestehende Datenquellen bearbeitet** werden
- Über den "Delete"-Button können **bestehende Datenquellen gelöscht** werden
- Über den "Deactivate"-Button können **bestehende Datenquellen deaktiviert / aktiviert** werden

```{note}
Eine deaktivierte Datenquelle bleibt im System enthalten, wird allerdings vom Scheduler nicht ausgeführt. Bei der Deaktivierung einer Datenquelle werden alle Objekte (Meldungen, Fahrten, Fahrzeuge), die in Zusammenhang mit dieser Datenquelle stehen, gelöscht. Nach der Aktivierung wird die Datenquelle zum nächsten regulären Zeitpunkt vom Scheduler ausgeführt.
```

(h-datasources-general-edit)=

## Anlegen, Bearbeiten und Löschen von Datenquellen

Um eine neue Datenquelle anzulegen, klicken Sie auf den "Hinzufügen"-Button oben rechts. Bestehende Datenquellen können über den "Edit"-Button in der entsprechenden Zeile bearbeitet werden. Die Bearbeitung erfolgt in folgendem Dialog:

```{figure} ../_static/images/datasources-basedata-screen.png
:name: img-datasources-basedata-screen
```

Für jede Datenquelle können folgende Informationen gepflegt werden:
- **Name**: _eindeutige Bezeichnung_ innerhalb des Systems für die Datenquelle
- **Adapter**: Typ der Datenquelle (GTFS-RT, SIRI-Lite, SIRI-...)
- **Endpunkt-URL**: URL, von der die Daten bei der Ausführung der Datenquelle abgerufen werden
- **Cron-Ausdruck**: Cron-Ausdruck zur Angabe der gewünschten Ausführungsintervalle
- **Verfahrensweise bei ungültigen Bezügen**: Angabe zum Umgang mit Objekten mit ungültigen Bezügen
- **Aktiv**: Aktivierung oder Deaktivierung der Datenquelle
- **Log Dumps**: Aktivierung oder Deaktivierung der Log-Dump, bei Deaktivierung werden nur die Log-Metadaten gespeichert

Neben diesen Parametern können in Abhängigkeit vom Adapter-Typ weitere, dynamische Parameter gepflegt werden.

Für jede Datenquelle können außerdem sogenannte **Mappings** und **Anreicherungen** definiert werden.

Bestätigen Sie den Dialog mit Klick auf "Speichern". Im Anschluss wird die Datenquelle in der Übersicht angezeigt und kann sofort verwendet werden.

(h-datasources-invalid-reference-policies)=

### Verfahrensweisen bei ungültigen Bezügen

Wenn ein Objekt nach dem Mapping keinem Objekt aus dem GTFS-Feed zugeordnet werden kann, gibt es verschiedene Verfahrensweisen zum Umgang mit diesem Objekt.

- **keine Angabe**: Auch bei ungültigen Bezügen wird das aus der Datenquelle synchronisierte Objekt gespeichert.
- **gesamtes Objekt verwerfen**: Sobald an einem synchronisierten Objekt ein Bezug ungültig ist, wird das Objekt aus dem aktuellen Lauf verworfen. Existiert bereits ein passendes Objekt aus derselben Datenquelle, wird es gelöscht.
- **ungültige Bezüge verwerfen**:
	- Bei **Meldungen** werden ungültige Bezüge entfernt.
	- Bei **Fahrten** werden ungültige Haltestellenbezüge aus den Halteereignissen entfernt. Ungültige Linienbezüge werden nicht übernommen. Wenn kein gültiger Fahrtbezug vorliegt, wird die Fahrt deaktiviert.
	- Bei **Fahrzeugpositionen** werden ungültige Linienbezüge nicht übernommen. Wenn kein gültiger Fahrtbezug vorliegt, wird das Fahrzeug deaktiviert.
- **ungültige Bezugselemente verwerfen**:
	- Bei **Meldungen** werden ungültige Bezugselemente innerhalb eines Bezugs entfernt.
	- Bei **Fahrten** und **Fahrzeugpositionen** entspricht das Verhalten derzeit der Option **ungültige Bezüge verwerfen**.
- **gesamtes Objekt deaktivieren**: Das Objekt wird gespeichert, aber bei ungültigen Bezügen deaktiviert und dadurch in der GTFS-RT-Ausgabe unterdrückt. _Empfohlene Verfahrensweise für Fahrten und Fahrzeugpositionen._

(h-datasources-general-mapping)=

## Mapping

In vielen Fällen entsprechen die IDs aus externen Datenquellen nicht exakt den IDs im GTFS-Feed. Bei den meisten Objekten (Verkehrsunternehmen, Haltestellen, Linien, ...) ist das Matching der Daten nicht zielführend. Aus diesem Grund können in EchoGTFS sog. **Mappings** je Datenquelle definiert werden. Dabei handelt es sich um Schlüssel-Wert-Paare unter Angabe eines Objekttyps, auf den sich die Mappings beziehen.

Zum Bearbeiten der Mappings einer Datenquelle gehen Sie folgendermaßen vor:

1. Wechseln Sie im Bearbeitungsdialog der Datenquelle auf den Tab "Mapping"
2. Wählen Sie den gewünschten Objekttyp aus, für den Sie die Mappings bearbeiten wollen
3. Fügen Sie beliebig Mappings hinzu oder entfernen diese aus der Liste

```{figure} ../_static/images/datasources-mapping-screen.png
:name: img-datasources-mapping-screen
```

Wenn ein Schlüssel zu einer mehrdeutigen Zuordnung führt, wird der jeweils erste Treffer verwendet.

```{note}
Bei den Schlüsseln besteht die Möglichkeit, mittels "*" sogenannte Wildcards anzugeben. So greift beispielsweise ein Schlüssel mit "echo-700*" auf alle IDs des jeweiligen Objekttyps, die mit "echo-700" beginnen.
```

Neben der Bearbeitung in EchoGTFS können Sie außerdem die bestehenden Mappings als CSV exportieren oder importieren. Diese Funktion bietet sich besonders für die Massenbearbeitung von Mappings mit an. Außerdem werden Mappings im Rahmen der {ref}`h-system-copy-system-copy` mit übertragen.

(h-datasources-general-enrichment)=

## Anreicherung

Teilweise enthalten Daten aus externen Datenquellen nur unvollständige Informationen. Diese können daher in EchoGTFS basierend auf Regeln angereichert werden.

```{note}
Anreicherungen sind aktuell nur für Meldungen verfügbar.
```

Zum Bearbeiten der Anreicherungsregeln einer Datenquelle gehen Sie folgendermaßen vor:

1. Wechseln Sie im Bearbeitungsdialog der Datenquelle auf den Tab "Anreicherung"
2. Wählen Sie den gewünschten Anreicherungstyp aus, für den Sie die Regeln bearbeiten wollen
3. Fügen Sie beliebig Regeln hinzu oder entfernen diese aus der Liste

```{figure} ../_static/images/datasources-enrichments-screen.png
:name: img-datasources-enrichments-screen
```

Für jede Regel können Sie folgende Informationen angeben:

- **Quellfeld**: Feld(er), in denen nach dem Schlüssel gesucht wird
- **Schlüssel**: Suchtext, der zur Anwendung der Regel führt
- **Wert**: Ergebniswert, der für den jeweiligen Anreicherungstyp gesetzt wird
- **Priorität**: Priorisierte Reihenfolge der der Regeln

Regeln, die in der Priorität weiter oben stehen, werden vorrangig angewandt. Sobald eine Regel greift, werden andere Regeln nicht mehr geprüft. Die Schlüssel werden dabei unabhängig von Groß- und Kleinschreibung geprüft.

```{note}
Bei den Schlüsseln besteht die Möglichkeit, mittels "*" sogenannte Wildcards anzugeben. So greift beispielsweise ein Schlüssel mit "außer betrieb*" für die Texte "Rolltreppe auf Gleis 1 außer Betrieb", aber auch für "Aufzug außer Betrieb" im jeweiligen Quellfeld und kann damit für Meldungen auch mit unterschiedlichem Titel, aber derselben Auswirkung verwendet werden.
```
