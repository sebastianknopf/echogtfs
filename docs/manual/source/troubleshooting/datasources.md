# Datenqellen

**In den Logs einer Datenquelle wird kein Endpunkt angezeigt**

Dies ist typischerweise bei event-basierten Datenquellen der Fall. Da eine event-basierte Datenquelle die Daten aus dem Quellsystem nicht selbst aktiv anfragt, sondern die Daten vom Quellsystem übermittelt werden, ist der genaue Endpunkt nicht bekannt.

**Der Download-Button bei den Log-Einträgen ist deaktiviert**

Prüfen Sie, ob für die Datenquelle das Log Dumping aktiviert ist. Falls nicht, werden standardmäßig nur die Meta-Informationen (wie bspw. Statuscode, Datenmenge, ...) eines Durchlaufs gespeichert.

**Eine Haltestelle wird als Zusatzhalt erkannt, dafür werden andere Haltestellen als Haltausfall im Fahrtverlauf angezeigt**

Prüfen Sie, ob die Behandlung von unerwarteten / fehlenden Haltestellen als Zusatzhalt / Haltausfall in den Einstellungen der jeweiligen Datenquelle aktiviert ist. Wenn die Option deaktiviert wird, werden unerwartete und fehlende Haltestellen-IDs ignoriert.

 **Eine Haltestellen-ID wird als ungültig, aber nicht als Zusatzhalt angezeigt, obwohl die Behandlung von unerwarteten / fehlenden Haltestellen-IDs als Zusatzhalt / Haltausfall in der Datenquelle aktiviert ist**

Wenn es sich bei der Haltestellen-ID um eine globale Haltestellen-ID (im Sinne von DHID, SLOID, ...) handelt, wird bei der Überprüfung nur der Anteil _bis zur Haltestellenebene_ herangezogen. Das bedeutet, dass die Haltestelle selbst nicht als Zusatzhalt interpretiert wird, gleichzeitig die _vollständige Haltestellen-ID_ dennoch nicht im statischen GTFS-Feed fehlen kann und daher als ungültig eingestuft wird. Dasselbe gilt sinngemäß für die Erkennung von Haltausfällen aufgrund einer vermeintlich fehlenden Haltestelle im Fahrtverlauf.