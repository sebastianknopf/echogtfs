# Ersteinrichtung

Die wichtigste Datengrundlage von EchoGTFS ist ein statischer GTFS-Feed. Basierend auf diesem GTFS-Feed werden die gültigen Referenzen der GTFS-RT-Daten aufgebaut.

Um einen statischen GTFS-Feed zu laden, gehen Sie folgendermaßen vor:

1. Loggen Sie sich mit Ihren Zugangsdaten in EchoGTFS ein
2. Wechseln Sie in der Seitenleiste in den Bereich "Einstellungen"
3. Scrollen Sie in den Abschnitt "GTFS-Feed"

```{figure} ../_static/images/gtfs-settings-screen.png
:name: img-initial-setup-gtfs-settings-screen
```

4. Geben Sie im entsprechenden Feld eine gültige URL ein, von der der statische GTFS-Feed abgerufen werden kann.
5. Geben Sie außerdem einen gültigen Cron-Ausdruck an um zu steuern, wann der statische GTFS-Feed automatisch geupdated werden soll.
6. Optional: Klicken Sie auf "importieren", um den statischen GTFS-Feed sofort zu laden. Dieser Vorgang kann einige Minuten in Anspruch nehmen.

Nach erfolgreichem Import stehen die Daten aus dem statischen GTFS-Feed als Referenz zur Verfügung. Sie können das außerdem überprüfen, indem Sie eine manuell eine Meldung erfassen und dort entsprechende Bezüge auswählen.