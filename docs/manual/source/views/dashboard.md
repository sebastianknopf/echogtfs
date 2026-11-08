# Dashboard

Das Dashboard zeigt eine Übersicht über den aktuellen Systemstatus.

```{figure} ../_static/images/dashboard-overview-screen.png
:name: img-dashboard-overview-screen
```

- Für alle Objekte wird die Anzahl der **aktuell aktivierten Objekte** und die Anzahl der inaktiven Objekte angezeigt.
- Bei **Fahrten** wird weiter zwischen **aktiven** und **überwachten** Fahrten differenziert. Eine aktive Fahrt ist dabei eine Fahrt, die Prognosedaten enthält und auch mit diesen nach außen kommuniziert wird. Eine überwachte Fahrt ist eine Fahrt, die von EchoGTFS bereits erkannt und gematched wurde, aber noch keine Prognosedaten enthält. Generell können hierbei auch Fahrten enthalten sein, die planmäßig noch nicht verkehren und in der Zukunft liegen.
- Unterhalb werden verschiedene KPIs angezeigt:
    - **Solldaten**: Zeigt den letzten Importzeitstempel und -Status, sowie die Anzahl der derzeit geladenen Fahrten im Soll-Fahrplan an.
    - **Echtzeit**: Zeigt die Anzahl der aktuell planmäßig verkehrenden Fahrten und deren Echtzeitquote an. Hier werden nur Fahrten einbezogen, für die auch Prognosedaten vorliegen.
    - **Fahrzeuge**: Zeigt die Anzahl der aktuell planmäßig verkehrenden Fahrten und deren Quote mit Zuordnung eines Fahrzeuges an.
    - **Konflikte**: Zeigt die Anzahl Fehler und Warnungen im System an.
- Im Abschnitt **Dienste** wird der Status verschiedener Zusatzdienste angezeigt, sofern diese bei der Installation aktiviert werden. Dazu zählen beispielsweise die SIRI-Dienste.