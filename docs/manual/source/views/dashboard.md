# Dashboard

Das Dashboard zeigt eine Übersicht über den aktuellen Systemstatus.

```{figure} ../_static/images/dashboard-overview-screen.png
:name: img-dashboard-overview-screen
```

- Für alle Objekte wird die Anzahl der **aktuell aktivierten Objekte** und die Anzahl der inaktiven Objekte angezeigt
- Bei **Fahrten** wird weiter zwischen **aktiven** und **überwachten** Fahrten differenziert. Eine aktive Fahrt ist dabei eine Fahrt, die Prognosedaten enthält und auch mit diesen nach außen kommuniziert wird. Eine überwachte Fahrt ist eine Fahrt, die von EchoGTFS bereits erkannt und gematched wurde, aber noch keine Prognosedaten enthält
- Im unteren Bereich werden die jeweils konfigurierten öffentlichen GTFS-RT Endpunkte angezeigt
    - Über die Buttons "PBF" und "JSON" werden die URLs in die Zwischenablage kopiert, die zum Abruf der Daten als **ProtoBuf** und **JSON** verwendet werden können