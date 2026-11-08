(h-conflicts-conflicts)=

# Konfliktmonitoring

In EchoGTFS können Konflikte in den eingehenden Daten anhand verschiedener Kriterien überwacht werden. Über den Eintrag "Konflikte" in der Seitenleiste sehen Sie eine Übersicht über alle aktuell vorliegenden Konflikte:

```{figure} ../_static/images/conflicts-overview-screen.png
:name: img-conflicts-conflicts-overview-screen
```

- Im oberen Bereich muss immer eine **Datenquelle** ausgewählt werden, für die die Konflikte angezeigt werden. Standardmäßig ist die erste Datenquelle gewählt.
- Weiter lassen sich über **CSV exportieren** die Konflikte als CSV-Datei zur Weiterverarbeitung beispielsweise an Datenprovider exportieren.
- Über den Filter können verschiedene Konflikttypen ein- oder ausgeblendet werden.

Zu jedem Konflikt wird der **Typ** (Warnung oder Fehler) über ein entspr. Icon und den Text, der **Zeitpunkt**, zu dem der Konflikt erstmalig aufgetreten ist und ein **Fehlercode** angezeigt. Weiter werden zu jedem Konflikt abhängig vom Konflikttyp und der Herkunft verschiedene, zusätzliche **Eigenschaften** mit übermittelt, die unterhalb als Liste angezeigt werden. Über diese Eigenschaften ist es beispielsweise möglich zu erkennen, wieso eine Fahrt nicht zugeordnet werden konnte und welche Eingangsdaten von der Datenquelle übergeben wurden.

## Voraussetzungen und Grenzen

EchoGTFS überwacht nicht die eingehenden Rohdaten, sondern den Import der Daten und die während des Imports ermittelten Konflikte. Aus diesem Grund stehen die Möglichkeiten zum Konfliktmonitoring in direktem Zusammenhand mit der Art und Weise, wie EchoGTFS verwendet wird. Grundsätzlich gilt, dass Konflikte, die beispielsweise aufgrund der {ref}`eingestellten Verfahrensweise bei ungültigen Bezügen  <h-datasources-invalid-reference-policies>` erst gar nicht entstehen können, im Konfliktmonitoring nicht in Erscheinung treten.

Für die Verfahrensweisen **gesamtes Objekt verwerfen**, **ungültige Bezüge entfernen** und **ungültige Bezugselemente entfernen** werden die Datenobjekte und deren Elemente verworfen, sodass sie im Konfliktmonitoring erst gar nicht auftauchen.

Datenobjekte, die bereits während des Imports von der jeweiligen Datenquelle verworfen werden, werden im Konfliktmonitoring **nicht erfasst**.

## Externe Anbindung

Da das Konfliktmonitoring keine historischen Daten speichert und stets den aktuellen Systemzustand zeigt, können sämtliche Konflikte auch über die {ref}`h-echo-api-echo-api` von externen Systemen zur Historisierung abgefragt und gespeichert werden.
