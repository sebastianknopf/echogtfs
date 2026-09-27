# GTFS-RT

**Bei einer Fahrt wird das Feld start_time und an den StopEvents die stop_sequence nicht mit ausgegeben**

Das Verhalten ist typisch für Fahrten, für die nur inkrementelle Updates vorliegen. Da bei inkrementellen Updates die genaue Fahrt-Startzeit und die exakte Nummer der Haltestelle in der Haltefolge in der Regel nicht ermittelt werden können, werden für unvollständige / inkrementelle Fahrten diese Informationen im GTFS-RT Datensatz nicht ausgegeben.

**Eine Meldung, eine Fahrt oder ein Fahrzeug wird nicht über GTFS-RT ausgegeben**

Prüfen Sie, ob das betroffene Objekt ggf. deaktiviert ist. Abhängig von der Konfiguration der Datenquelle kann es sein, dass Objekte nach der Synchronisation deaktiviert werden, weil beispielsweise Bezüge ungültig sind.