(h-system-settings-system-settings)=

# Systemeinstellungen

In den Systemeinstellungen können Sie grundlegende Einstellungen in EchoGTFS vornehmen. Die nachfolgenden Abschnitte beschreiben die Einstellungsmöglichkeiten und ihre Auswirkungen.

```{figure} ../_static/images/system-settings-overview-screen.png
:name: img-system-settings-system-settings-overview-screen
```

(h-system-settings-app-and-appearance)=

## Allgemein und Erscheinungsbild

Im Abschnitt "Allgemein" und "Erscheinungsbild" können Sie folgende Einstellungen vornehmen:

- **App-Titel**: Angezeigter Titel im Frontend von EchoGTFS
- **Primär- und Sekundärfarbe**: Farbschema im Frontend von EchoGTFS
- **Sprache**: Standardmäßig gewählte Sprache im Frontend von EchoGTFS

(h-system-settings-gtfs-rt)=

## GTFS-Realtime

Im Abschnitt "GTFS-Realtime" können Sie folgende Einstellungen vornehmen:

- **GTFS-RT ServiceAlerts Pfad**: Pfad zum GTFS-RT Endpunkt für ServiceAlerts
- **GTFS-RT TripUpdates Pfad**: Pfad zum öffentlichen GTFS-RT Endpunkt für TripUpdates
- **GTFS-RT VehiclePositions Pfad**: Pfad zum öffentlichen GTFS-RT Endpunkt für VehiclePositions
- **BasicAuth Benutzername:** _(optional)_ Benutzername um die GTFS-RT Endpunkte mit BasicAuth abzusichern
- **BasicAuth Passwort:** _(optional)_ Password um die GTFS-RT Endpunkte mit BasicAuth abzusichern

(h-system-settings-cleanup)=

## Datenbereinigung

Im Abschnitt "Datenbereinigung" können Sie das Verhalten des Berenigungs-Dienstes beeinflussen. Folgende Einstellungen stehen zur Verfügung:

```{note}
Der Berenigungs-Dienst bezieht sich aktuell ausschließlich auf Datenquellen-Logs und **interne Meldungen**. Datenquellen-Logs werden grundsätzlich **nach 24 Stunden** gelöscht. Objekte, welche über Datenquellen synchronisiert werden, werden vom Berenigungs-Dienst nicht verändert.
```

- **Cron-Ausdruck**: Cron-Ausdruck mit dem der Berenigungs-Dienst im Hintergrund ausgeführt wird
- **Verfahrensweise bei abgelaufenen Objekten**: Legt fest, ob abgelaufene Objekte **gelöscht** oder **deaktiviert** werden sollen
- **Endgültiges Löschen**: Legt fest, ab welchem Alter Objekte endgültig gelöscht werden
