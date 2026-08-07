# Meldungen

Im Bereich "Meldungen" werden alle aktuellen Meldungen angezeigt.

```{figure} ../_static/images/alerts-overview-screen.png
:name: img-alerts-overview-screen
```

- Im oberen Bereich besteht die Möglichkeit, die Meldungen nach Datum zu sortieren:
    - **neueste zuerst**: Zeigt die Meldungen mit dem aktuellsten Zeitstempel zuerst an
    - **älteste zuerst**: Zeigt die Meldungen mit dem ältesten Zeitstempel zuerst an
    - **Hinweis**: Meldungen ohne zeitlichen Bezug werden grundsätzlich am Anfang der Liste angezeigt
- Über den "Filter" lassen sich die Meldungen wie folgt filtern:
    - **aktive Meldungen**: Es werden alle aktivierten Meldungen mit einbezogen
    - **inaktive Meldungen**: Es werden alle deaktivierten Meldungen mit einbezogen
    - **interne Meldungen**: Es werden alle Meldungen mit einbezogen, die manuell in EchoGTFS erfasst wurden
    - **externe Meldungen**: Es werden alle Meldungen mit einbezogen, die aus einer externen Datenquelle synchronisiert wurden
- Für jede Meldung wird in der Übersicht folgende Informationen angezeigt:
    - **Titel**: Titel der ersten Sprache der Meldung
    - **Zeitraum**: Gültigkeits- und Veröffentlichungszeitraum der Meldung
    - **Bezüge**: Verkehrsunternehmen, Haltestellen und Linien, auf die sich eine Meldung bezieht
    - **Datenquelle**: Name der Datenquelle, wenn eine Meldung von einer externen Datenquelle synchronisiert wurde; ansonsten "Intern"
    - **Aktivierungsstatus**: Information, wenn eine Meldung deaktiviert wurde. Deaktivierte Meldungen werden in der GTFS-RT Ausgabe unterdrückt. Über den "On/Off" Button können Meldungen aktiviert oder deaktiviert werden.
    - **Fehlerstatus**: Rotes Warndreieck, wenn eine Meldung ungültige Bezüge aufweist. Solange die Meldung nicht deaktiviert ist, wird sie weiterhin über GTFS-RT ausgegeben und kann dadurch zu Fehlern bei Abnehmersystemen führen

Um die Details zu einer Meldung anzuzeigen, klicken Sie auf den "View" Button in der entsprechenden Zeile. Daraufhin wird folgender Dialog gezeigt, in dem alle wichtigen Informationen rund um die Meldung zu sehen sind:

```{figure} ../_static/images/alerts-detail-screen.png
:name: img-alerts-detail-screen
```

- Im oberen Bereich des Dialogs werden alle Basisdaten wie **Grund**, **Auswirkung** und **Schweregrad**, sowie **Gültigkeits- und Veröffentlichungszeiträume** der Meldung angezeigt
- Bezüge, zu denen **keine gültige Referenz in den GTFS-Daten** gefunden wurde, werden mit einem roten Ausrufezeichen gekennzeichnet. Typischerweise passiert das nur bei Meldungen, die aus externen Datenquellen synchronisiert wurden
- Im unteren Bereich des Dialogs werden alle Übersetzungen der jeweiligen Meldung mit **Titel**, **Beschreibungstext** und **optionaler URL** angezeigt

(h-alerts-create-or-edit)=

## Meldung erstellen, bearbeiten oder löschen

EchoGTFS bietet die Möglichkeit, Meldungen mit Bezug auf den GTFS-Feed manuell zu erfassen.

```{note}
Meldungen, welche aus externen Datenquellen synchronisiert wurden, können in EchoGTFS nicht manuell bearbeitet oder gelöscht werden. Wird eine Meldung manuell deaktiviert, bleibt dieser Aktivierungsstatus auch nach erneuter Synchronisation mit der Datenquelle bestehen, sofern sich die ID der Meldung selbst nicht ändert.
```

Klicken Sie zum Erfassen einer Meldung auf den Button "Erfassen" im oberen Bereich. Sie bekommen daraufhin folgenden Dialog angezeigt:

```{figure} ../_static/images/alerts-basedata-screen.png
:name: img-alerts-basedata-screen
```

Wählen Sie hier einen passenden Grund und eine Folge, sowie den Schweregrad der Meldung aus. Im nächsten Tab "Gültigkeit" haben Sie die Möglichkeit, einzelne Zeiträume für die **Gültigkeit** ("wann tritt die Auswirkung konkret in Kraft") und den **Veröffentlichungszeitraum** ("wann soll die Meldung in den Auskunftsmedien sichtbar sein") auszuwählen:

```{figure} ../_static/images/alerts-validity-screen.png
:name: img-alerts-validity-screen
```

Wenn Sie hier keinen Zeitraum angeben, ist die Meldung automatisch immer gültig und hat somit auch kein Ablaufdatum. Meldungen, die in EchoGTFS mit einem Ablaufdatum erstellt wurden, werden durch die {ref}`h-system-settings-cleanup` entsprechend deaktiviert und gelöscht.

Im nächsten Schritt können Sie mittels **Bezügen** auswählen, auf welche Objekte sich eine Meldung bezieht:

```{figure} ../_static/images/alerts-references-screen.png
:name: img-alerts-references-screen
```

Sobald Sie in die Eingabefelder einen Text eingeben, unterstützt Sie EchoGTFS bei der Auswahl mit passenden Vorschlägen.

Die **Bezugselemente** (Unternehmen, Linie, Haltestelle, Linientyp, Richtung) werden dabei immer als UND-Verknüpfung interpretiert. Wenn Sie beispielsweise eine Meldung für die Linie _701_ und die Haltestelle _Hauptbahnhof_ anlegen, wird diese Meldung von gängingen Auskunftssystemen nur für die Linie _701 an der Haltestelle Hauptbahnhof_ angezeigt. Soll die Meldung hingegen für mehrere Linien oder Haltestellen (oder andere Objekte) unabhängig voneinander gelten, müssen diese jeweils als eigene Bezüge angelegt werden. Die einzelnen Bezüge werden jeweils als ODER-Verknüpfung interpretiert.

Wenn Sie hier keinen Bezug angeben, ist die Meldung automatisch immer für alle Objekte aus dem GTFS-Feed gültig.

Im letzten Schritt geben Sie mindestens eine Übersetzung mit einem Titel und/oder Beschreibung an:

```{figure} ../_static/images/alerts-translations-screen.png
:name: img-alerts-translations-screen
```

Diese Informationen entsprechen der textuellen Beschreibung der Meldung. Über eine URL können Sie auf eine Webseite verweisen, auf der weitere Informationen enthalten sind.

Das **Bearbeiten** einer bestehenden, manuell erfassten Meldung erfolgt, indem Sie in der Übersicht auf den "Stift" Button klicken.

Um eine manuell erfasste Meldung zu **löschen**, klicken Sie auf den "Papierkorb" Button in der jeweiligen Zeile und bestätigen Sie den nachfolgenden Dialog.