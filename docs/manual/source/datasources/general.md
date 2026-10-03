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
Eine deaktivierte Datenquelle bleibt im System enthalten, wird allerdings vom Scheduler nicht ausgeführt. Bei der Deaktivierung einer Datenquelle werden alle Objekte (Meldungen, Fahrten, Fahrzeuge), die in Zusammenhang mit dieser Datenquelle stehen, gelöscht. Nach der Aktivierung wird die Datenquelle zum nächsten regulären Zeitpunkt oder eventbasiert über die {ref}`h-push-api-push-api` vom Scheduler ausgeführt.
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
- **Endpunkt-URL**: URL, von der die Daten bei der Ausführung der Datenquelle abgerufen werden. Optional bei eventbasierten Datenquellen, je nach verwendetem Adapter-Typ
- **Ausführungsart**: Ausführungsart der Datenquelle. Zeitbasiert = über Cron-Ausdruck, Eventbasiert = über {ref}`h-push-api-push-api`
- **Cron-Ausdruck**: Cron-Ausdruck zur Angabe der gewünschten Ausführungsintervalle. Nur relevant bei zeitbasierter Ausführung
- **Verfahrensweise bei ungültigen Bezügen**: Angabe zum Umgang mit Objekten mit ungültigen Bezügen
- **Aktiv**: Aktivierung oder Deaktivierung der Datenquelle
- **Differentielle Updates**: Aktivierung oder Deaktivierung von differentiellen Updates für die jeweilge Datenquelle
- **Log Dumps**: Aktivierung oder Deaktivierung der Log-Dump, bei Deaktivierung werden nur die Log-Metadaten gespeichert

Neben diesen Parametern können in Abhängigkeit vom Adapter-Typ weitere, dynamische Parameter gepflegt werden.

Für jede Datenquelle können außerdem sogenannte **Mappings** und **Anreicherungen** definiert werden.

Bestätigen Sie den Dialog mit Klick auf "Speichern". Im Anschluss wird die Datenquelle in der Übersicht angezeigt und kann sofort verwendet werden.

(h-datasources-filters)=

## Filter

Die meisten Datenquellen unterstützen Filter, um die zu verarbeitenden Daten möglichst früh einzuschränken. Hierzu können im Feld **Filter** in der Datenquellenkonfiguration Filterausdrücke in sogenannten Filterklassen angegeben werden. Folgende Filterklassen sind aktuell verfügbar:

- `operator`: Schränkt Daten basierend auf Betreiber- und Teilnehmerkennungen ein
- `line`: Schränkt Daten basierend auf der verwendeten Linienkennung ein

Bei der Eingabe wird folgende Syntax verwendet: `[Filterklasse]/[Filterausdruck]`

Die Filterausdrücke **innerhalb einer Filterklasse** mit logisch ODER behandelt, Filterausrücke **aus verschiedenen Filterklassen** werden mit logisch UND behandelt.

In allen Filterausdrücken kann das Zeichen `*` als Wildcard für "beliebig viele Zeichen" eingesetzt werden, um beispielsweise auf bestimmte Linien einschränken zu können, ohne dabei explizit alle Linien anzugeben. Je nach Datenquellentyp werden die Filter auf Client- oder Serverseite berücksichtigt.

_Die genauen Regeln zur Unterstützung von Filtern sind in der Beschreibung der jeweiligen Datenquelle enthalten. Nicht alle Datenquellen unterstützen automatisch alle Filterklassen._

(h-datasources-time-vs-event-based)=

## Zeit- und Eventbasierte Ausführung

Standardmäßig werden Datenquellen zeitbasiert ausgeführt. Dabei werden sie vom internen Scheduler zu regelmäßgen, über den Cron-Ausdruck definierten Zeitpunkten ausgeführt. Die Daten werden dabei von EchoGTFS vom Quellsystem abgefragt.

Bei besonders zeitkritischen Datenquellen (z.B. Fahrzeugpositionen) besteht alternativ die Möglichkeit, die Datenquelle eventbasiert auszuführen. Dabei werden die Daten aktiv vom Quellsystem an den Endpunkt der {ref}`h-push-api-push-api` für die jeweilige Datenquelle übermittelt und die Datenquelle unmittelbar ausgeführt.

(h-datasources-differential-incremental-updates)=

## Differentielle und Inkrementelle Updates

Grundsätzlich gehen Datenquellen immer davon aus, dass der vollständige aktuellen Datenstand eines Quellsystems übermittelt wird. Ausgehend von diesem Datenstand werden alle Daten in EchoGTFS für die jeweilge Datenquelle synchronisiert. Dabei werden neue Objekte hinzugefügt, bestehende Objekte geupdated und nicht mehr vorhandene Objekte gelöscht. Als Alternative bieten sich differentielle und inkrementelle Updates, insbesondere bei event-basierten Datenquellen an, um die Rechenleistung und die Menge der mit jedem Durchlauf zu verarbeitenden Daten drastisch zu reduzieren.

Bei **differentiellen Updates** werden hingegen nur noch die Änderungen an Objekten synchronisiert, aber keine Objekte mehr implizit gelöscht. Stattdessen müssen die Objekte durch die Datenquelle mittels eines entsprechenden Delete-Flags gelöscht werden. Wird ein Objekt nicht explizit durch ein solches Delete-Flag gelöscht, wird das Objekt stattdessen durch den internen Cleanup-Service aufgegriffen und nach der konfigurierten Zeit gelöscht. Damit eine Datenquelle differentielle Updates verarbeitet, muss dies an der jeweiligen Datenquelle aktiviert werden.

Mit **inkrementellen Updates** werden nur einzelne Eigenschaften von Objekten (z.B. die Pünktlichkeitsprognose bei einer Fahrt) geupdated. Aktuell werden inkrementelle Updates **nur für Fahrten** unterstützt. Im Optimalfall wird dabei zunächst eine sogenanne Komplettfahrt übermittelt, bei der alle Eigenschaften einer Fahrt einmal vollständig enthalten sind. Mit den folgenden Updates wird dann die Prognose für einzelne Haltestellen überschrieben. In diesem Fall schreibt EchoGTFS die Prognose dann auf alle nachfolgenden Haltestellen fort, bis entweder die letzte Haltestelle erreicht ist, oder abweichende Prognosedaten für eine Haltestelle in dem Update vorliegen. Werden hingegen von Anfang an nur inkrementelle Updates für eine Fahrt gesandt, so werden die nur die Daten aus dem jeweils letzten Update gespeichert. Inkrementelle Updates werden standardmäßig unterstützt, da die Information, dass es sich um ein inkrementelles Update handelt, aus den Daten selbst hervorgeht. Eine gesonderte Aktivierung ist daher nicht notwendig.

(h-datasources-invalid-reference-policies)=

## Verfahrensweisen bei ungültigen Bezügen

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

(h-datasources-general-performance)=

## Performance

Die Datenquellen sind darauf ausgerichtet, Massendaten zu verarbeiten. Entscheidend für die Durchlaufzeit einer Datenquelle sind insbesondere Netzwerkverbindung und Prozessorleistung des Systems, auf dem EchoGTFS läuft. Neben diesen Faktoren gibt es noch weitere Einflussfaktoren, die die Durchlaufzeit eines Datenupdates maßgeblich beeinflussen können:

- **Anzahl der zu verarbeitetenden Objekte**: Insbesondere Datenquellen, die Prognosedaten verarbeiten, haben eine vergleichsweise hohe Last auf der Datenbank, da in kurzer Zeit eine Vielzahl von Objekten ersetzt werden müssen. Nutzen Sie insbesondere bei großen, konsoldierten Datenquellen Filter, um die zu verarbeitenden Objekte von vorneherein auf ein sinnvolles Maß einzuschränken.
- **Verfahrensweise bei ungültigen Bezügen**: Wenn hier eingestellt ist, dass alle Objekte geladen, aber ggf. deaktiviert werden sollen, werden deutlich mehr Daten in die Datenbank geschrieben, als letztendlich über GTFS-RT veröffentlicht werden. Das ist gut für Monitoring-Zwecke, erhöht aber gleichzeitig die Durchlaufzeit eines Datenupdates erheblich, wenn die Anzahl der zu verarbeitenden Objekte dadurch ansteigt.

Weitere Performancesteigerungen lassen sich durch gezieltes Einsetzen von Filtern erreichen. Die Filter werden dabei - je nach Datenquelle und verwendetem Dialekt - client- oder bereits serverseitig berücksichtigt.

Durch Anwendung von {ref}`event basierten Datenquellen <h-datasources-time-vs-event-based>` und {ref}`differentiellen/inkrementellen Updates <h-datasources-differential-incremental-updates>` kann die Performance bei der Verarbeitung signifikant steigern.

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
