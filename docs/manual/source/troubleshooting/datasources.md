# Datenqellen

##### Eine Haltestelle wird als Zusatzhalt erkannt, dafür werden andere Haltestellen als Haltausfall im Fahrtverlauf angezeigt

Prüfen Sie, ob die Behandlung von unerwarteten / fehlenden Haltestellen als Zusatzhalt / Haltausfall in den Einstellungen der jeweiligen Datenquelle aktiviert ist. Wenn die Option deaktiviert wird, werden unerwartete und fehlende Haltestellen-IDs ignoriert.

##### Eine Haltestellen-ID wird als ungültig, aber nicht als Zusatzhalt angezeigt, obwohl die Behandlung von unerwarteten / fehlenden Haltestellen-IDs als Zusatzhalt / Haltausfall in der Datenquelle aktiviert ist

Wenn es sich bei der Haltestellen-ID um eine globale Haltestellen-ID (im Sinne von DHID, SLOID, ...) handelt, wird bei der Überprüfung nur der Anteil _bis zur Haltestellenebene_ herangezogen. Das bedeutet, dass die Haltestelle selbst nicht als Zusatzhalt interpretiert wird, gleichzeitig die _vollständige Haltestellen-ID_ dennoch nicht im statischen GTFS-Feed fehlen kann und daher als ungültig eingestuft wird. Dasselbe gilt sinngemäß für die Erkennung von Haltausfällen aufgrund einer vermeintlich fehlenden Haltestelle im Fahrtverlauf.