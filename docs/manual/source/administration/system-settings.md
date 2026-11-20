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

## Konfiguration GTFS-Realtime

Im Abschnitt "GTFS-Realtime" können Sie folgende Einstellungen vornehmen:

- **GTFS-RT ServiceAlerts Pfad**: Pfad zum GTFS-RT Endpunkt für ServiceAlerts
- **GTFS-RT TripUpdates Pfad**: Pfad zum öffentlichen GTFS-RT Endpunkt für TripUpdates
- **GTFS-RT VehiclePositions Pfad**: Pfad zum öffentlichen GTFS-RT Endpunkt für VehiclePositions
- **BasicAuth Benutzername:** _(optional)_ Benutzername um die GTFS-RT Endpunkte mit BasicAuth abzusichern. Leer lassen, um BasicAuth für die GTFS-RT Endpunkte zu deaktivieren
- **BasicAuth Passwort:** _(optional)_ Passwort um die GTFS-RT Endpunkte mit BasicAuth abzusichern. Leer lassen, um das bestehende Passwort weiter zu verwenden
- **Fahrten ohne Echtzeitdaten aus TripUpdates ausschließen**: Schließt überwachte Fahrten (siehe dazu {ref}`h-trips-trips`) aus dem GTFS-RT feed aus

(h-system-settings-push-api)=

## Konfiguration Push-API

Im Abschnitt "Push-API" können Sie folgende Einstellungen vornehmen:

- **Push-API Aktiv**: Schaltet die Push-API für eventbasierte Datenquellen frei
- **BasicAuth Benutzername:** _(optional)_ Benutzername umd ie Push-API mit BasicAuth abzusichern. Leer lassen, um BasicAuth für die Push-API zu deaktivieren
- **BasicAuth Passwort:** _(optional)_ Passwort um die Push-API mit BasicAuth abzusichern. Leer lassen, um das bestehende Passwort weiter zu verwenden

Die Push-API wird benötigt, um eventbasierte Schnittstellen aus externen Systemen ansprechen zu können.

(h-system-settings-cleanup)=

## Konfiguration Datenbereinigung

Im Abschnitt "Datenbereinigung" können Sie das Verhalten des Bereinigungs-Dienstes beeinflussen. Folgende Einstellungen stehen zur Verfügung:

- **Cron-Ausdruck**: Legt fest, wann der Bereinigungs-Dienst ausgeführt wird.
- **Verfahrensweise bei abgelaufenen Meldungen**: Legt fest, ob abgelaufene Meldungen deaktiviert oder gelöscht werden.
- **Endgültiges Löschen abgelaufener Meldungen**: Legt fest, nach wie vielen Tagen interne oder aus differentiellen Datenquellen stammende abgelaufene Meldungen endgültig gelöscht werden. **Niemals** deaktiviert diese altersbasierte Löschung; die Verfahrensweise **Löschen** entfernt solche Meldungen bereits bei Ablauf.
- **Maximales Alter für Fahrten**: Fahrten werden gelöscht, wenn das Ende ihrer letzten Haltestelle länger als das eingestellte Alter zurückliegt. Echtzeitzeiten haben Vorrang vor Fahrplanzeiten; fehlen diese, gelten das geplante Fahrtende oder die letzte Aktualisierung.
- **Maximales Alter für Fahrzeuge**: Fahrzeugpositionen werden gelöscht, wenn ihre letzte Aktualisierung länger als das eingestellte Alter zurückliegt.

```{note}
Bei **Deaktivieren** werden aktive abgelaufene Meldungen deaktiviert. Sofortige und altersbasierte Löschungen betreffen nur interne Meldungen und Meldungen aus differentiellen Datenquellen. Fahrten und Fahrzeugpositionen werden nach den jeweiligen Altersgrenzen gelöscht. Datenquellen-Logs werden **nach 24 Stunden** gelöscht.
```
