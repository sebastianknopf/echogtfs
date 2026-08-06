(h-system-copy-system-copy)=

# Systemkopie

Über die Funktion "Systemkopie" besteht die Möglichkeit, zentrale Systemkonfigurationen zwischen verschiedenen EchoGTFS-Instanzen zu übertragen. Dies bietet sich besonders an, wenn Einstellungen zunächst in einer Testumgebung validiert werden und später in eine Produktivumgebung umgezogen werden sollen.

Zum Export stehen folgende Bereiche bereit:

```{figure} ../_static/images/system-copy-overview-screen.png
:name: img-system-copy-system-copy-overview-screen
```

- **Systemeinstellungen**: Umfasst alle Systemeinstellungen zum Erscheinungsbild, GTFS-RT und Datenbereinigung
- **GTFS-Einstellungen**: Umfasst die Einstellungen rund um den GTFS-Import
- **Benutzer**: Umfasst die hinterlegten Accounts
- **Datenquellen**: Umfasst die hinterlegten Datenquellen inklusive deren Mappings und Anreicherungsdefinitionen

## Export

Um eine Systemkopie zu exportieren, gehen Sie folgendermaßen vor:

1. Wechseln Sie in der Seitennavigation in den Bereich "Einstellungen"
2. Wählen Sie im Abschnitt "Systemkopie" die Bereiche aus, welche kopiert werden sollen
3. Klicken Sie auf den Button "Exportieren" und speichern Sie die erhaltene ZIP-Datei

## Import

Um eine Systemkopie zu importieren, gehen Sie folgendermaßen vor:

1. Klicken Sie auf den Button "Importieren" und wählen Sie die zuvor exportierte ZIP-Datei aus
2. Warten Sie, bis EchoGTFS die Systemkopie importiert hat und validieren Sie die Einstellungen

```{note}
Beim Export kann eingestellt werden, welche Bereiche exportiert werden sollen. Beim Import werden grundsätzlich alle Daten innerhalb der Systemkopie importiert. Eine implizite Löschung von Informationen (d.h. ein Objekt, welches in der Systemkopie _nicht_ enthalten ist, wird auch in der Zielinstanz nicht gelöscht) findet nicht statt.

Bestehende Informationen (insbesondere Datenquellen und Accounts) werden allerdings im Zweifel überschrieben. Als Identifikation für Accounts gilt der **Username**, als Identifikation für Datenquellen gilt der **Name der Datenquelle**.
```