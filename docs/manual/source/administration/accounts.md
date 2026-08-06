(h-accounts-accounts)=

# Accounts

Zur Verwaltung der Accounts in EchoGTFS wechseln Sie über das Seitenmenü in den Bereich "Einstellungen". Dort sehen Sie eine Übersicht über alle existierenden Accounts:

```{figure} ../_static/images/accounts-overview-screen.png
:name: img-accounts-accounts-overview-screen
```

Jeder Account kann mit verschiedenen Rechten ausgestattet werden. Derzeit gibt es folgende Rechte:

- **Standard**: Darf in EchoGTFS Meldungen, Fahrten und Fahrzeuge sehen, sowie manuell Meldungen erfassen.
- **Poweruser**: Darf zusätzlich Einstellungen an Datenquellen vornehmen.
- **Admin**: Darf zusätzlich Systemeinstellungen und Accounts ändern.

Außerdem besteht die Möglichkeit, einen Account vorübergehend zu deaktivieren.

(h-accounts-new-account)=

## Account anlegen

Um einen neuen Account hinzuzufügen, klicken Sie auf den Button "Neuer Account". Geben Sie dann alle geforderten Informationen in den entsprechenden Dialog ein:

```{figure} ../_static/images/accounts-new-account-screen.png
:name: img-accounts-accounts-new-account-screen
```

Weisen Sie dem Account außerdem entsprechende Rechte zu und aktivieren Sie ihn.

Bestätigen Sie den Dialog mit Klick auf "Speichern". Im Anschluss wird der neue Account in der Übersicht angezeigt und kann sofort verwendet werden.

(h-accounts-edit-account)=

## Account bearbeiten

Um einen bestehenden Account zu bearbeiten, klicken Sie in der entsprechenden Zeile auf den Stift. Ändern Sie im nachfolgend angezeigten Dialog die Daten nach Ihren Wünschen ab:

```{figure} ../_static/images/accounts-edit-account-screen.png
:name: img-accounts-accounts-edit-account-screen
```

Auf diesem Weg können Sie beispielsweise auch einen bestehenden Account **aktivieren oder deaktivieren**, **andere Rechte zuweisen** oder das **Passwort ändern**. Wenn das bestehende Passwort beibehalten werden soll, lassen Sie das Feld einfach leer.

(h-accounts-delete-account)=

## Account löschen

Um einen bestehenden Account zu löschen, klicken Sie in der entsprechenden Zeile auf den Papierkorb. Bestätigen Sie den nachfolgenden Dialog entsprechend.

```{warning}
Ein gelöschter Account kann nicht wieder hergestellt werden! Exportieren Sie im Zweifel ein Backup über die {ref}`h-system-copy-system-copy`.
```