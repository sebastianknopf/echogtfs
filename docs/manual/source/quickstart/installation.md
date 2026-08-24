# Installation

(h-installation-system-requirements)=

## Systemvoraussetzungen

Zum Betrieb von EchoGTFS müssen mindestens folgende Anforderungen erfüllt sein:

- Git zum Download und der Versionsverwaltung
- Docker Engine und docker compose zum Verwalten der Container
- Mindestens 50GB Speicher
- Mindestens 8GB RAM
- ReverseProxy oder LoadBalancer für den Netzwerkverkehr

(h-installation-download-and-version)=

## Download und Versionsauswahl

Zur Installation sind folgende Schritte notwendig:

1. Download & Version

Laden Sie die aktuelle Version von EchoGTFS mit folgendem Kommando an einen Verzeichnispfad Ihrer Wahl (unter Ubuntu z.B. `/usr/local/docker/echogtfs`):

```shell
git clone https://github.com/sebastianknopf/echogtfs.git
```

Checken Sie als nächstes die gewünschte Version aus, sofern Sie nicht mit der aktuellen Version `latest` arbeiten wollen:

```shell
git checkout 1.1.0
```

(h-installation-setup-envs)=

## Einrichtung Umgebungsvariablen

Kopieren Sie die Datei `.env.example` und benennen Sie diese um zu `.env`. Öffnen Sie die Datei und legen Sie folgende Umbebungsvariablen fest:

`TIMEZONE`: Zeitzone, in der Sie die EchoGTFS-Instanz betreiben (z.B. `Europe/Berlin`)
`SECRET_KEY`: 32-stelliger zufälliger Schlüssel zur Authentifizierung und Authentisierung im Frontend
`FIRST_SUPERUSER`, `FIRST_SUPERUSER_EMAIL`, `FIRST_SUPERUSER_PASSWORD`: Initiale Zugangsdaten, mit denen Sie sich erstmalig bei EchoGTFS anmelden

`DOCS_ENABLED`: Option, um den für den externen Zugriff vorgesehenen Anteil der API zu veröffentlichen. Wenn dieser Wert auf `true` gesetzt wird, ist die Swagger Dokumentation unter `https://{domain}/api/swagger` erreichbar.

(h-installation-startup)=

## Start der Anwendung

Wenn soweit alle Konfigurationen vorgenommen sind, starten Sie EchoGTFS, indem Sie folgendes Kommando im Projektverzeichnis ausführen:

```shell
docker compose up -d --build
```

Dieser Vorgang kann einige Minuten dauern. Nach erfolgreichem Start sollte die Konsole etwa folgenden Text zeigen:

```shell
 ✔ backend                         Built
 ✔ frontend                        Built
 ✔ Container echogtfs-redis-1      Healthy
 ✔ Container echogtfs-database-1   Healthy
 ✔ Container echogtfs-backend-1    Started
 ✔ Container echogtfs-frontend-1   Started 
```

Ab diesem Zeitpunkt steht Ihnen das Frontend zum Login unter `http://localhost` zur Verfügung.

(h-installation-setup-reverse-proxy)=

## Betrieb mit ReverseProxy

Im Produktivbetrieb empfiehlt es sich, EchoGTFS hinter einem ReverseProxy oder LoadBalancer zu betreiben. Dieser ermöglicht einerseits, EchoGTFS mit einem anderen Frontend-Port zu betreiben, falls dies auf Ihrer Umgebung notwendig ist und zudem die Einbindung weiterer Absicherungsmechanismen, wie Authentifizierungsverfahren mit OAuth, IP-Whitelisting, mTLS oder VPN.

Eine Beispielhafte Konfiguration für Apache2 sieht folgenermaßen aus:

```
<VirtualHost *:443>

        ServerName echogtfs.your-domain.com

        ProxyPreserveHost On

        ProxyPass / http://127.0.0.1:8089/
        ProxyPassReverse / http://127.0.0.1:8089/

        SSLCertificateFile /etc/ssl/ssl_certificate.cer
        SSLCertificateKeyFile /etc/ssl/private_key.key
        SSLCertificateChainFile /etc/ssl/ssl_certificate_INTERMEDIATE1.cer

</VirtualHost>
```

In dieser Konfiguration wird davon ausgegangen, dass EchoGTFS lokal unter Port `8089` läuft.

(h-installation-first-login)=

## Erstanmeldung

Nachdem die Installation vorgenommen wurde, öffnen Sie EchoGTFS über den Browser. Sie sehen dann folgende Loginmaske:

```{figure} ../_static/images/login-screen.png
:name: img-installation-login-screen
```

Geben Sie hier die zuvor definierten Initialzugangsdaten ein. Wechseln Sie dann Ihr Passwort umgehend, indem Sie oben in der Kopfzeile auf das mittlere der beiden Icons klicken und dann "Passwort ändern" auswählen:

```{figure} ../_static/images/topbar-screen.png
:name: img-installation-topbar-screen
```

Geben Sie in dem nachfolgenden Dialog dann Ihr aktuelles Passwort, sowie das gewünschte neue Passwort inklusive Bestätigung ein. Das Passwort können Sie jederzeit ändern.

Außerdem besteht über das linke Icon die Möglichkeit, die **Sprache zu ändern**. Über das rechte Icon werden Sie aus EchoGTFS **ausgeloggt**.
