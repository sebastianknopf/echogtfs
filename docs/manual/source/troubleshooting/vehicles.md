# Fahrzeuge

**Obwohl über die Datenquelle Fahrzeuginformationen eingehen, werden die Fahrzeuge alle deaktiviert und keiner Fahrt zugeordnet**

Abhängig von der verwendeten Datenquelle und deren konkreter Umsetzung kann es sein, dass die enthaltenen Informationen zum Matching auf eine Fahrt nicht ausreichen, sofern die IDs nicht direkt zum Soll-Fahrplan passen. Sofern zum selben Quellsystem auch eine Anbindung zur Übermittlung von Fahrten besteht, kann diese ggf. genutzt werden, um die Fahrten zunächst dem Soll-Fahrplan zuzuordnen und über die gecacheten Fahrt-IDs dann eine Zuordnung der Fahrzeuge zu ermöglichen.