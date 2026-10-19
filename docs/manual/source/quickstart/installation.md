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

- `TIMEZONE`: Zeitzone, in der Sie die EchoGTFS-Instanz betreiben (z.B. `Europe/Berlin`)
- `SECRET_KEY`: 32-stelliger zufälliger Schlüssel zur Authentifizierung und Authentisierung im Frontend
- `FIRST_SUPERUSER`, `FIRST_SUPERUSER_EMAIL`, `FIRST_SUPERUSER_PASSWORD`: Initiale Zugangsdaten, mit denen Sie sich erstmalig bei EchoGTFS anmelden

- `DOCS_ENABLED`: Option, um den für den externen Zugriff vorgesehenen Anteil der API zu veröffentlichen. Weitere Informationen im Abschnitt {ref}`h-monitoring-api-monitoring-api`

### Weitere Umgebungsvariablen

Neben den eingangs erklärten Umgebungsvariablen gibt es noch weitere Umgebungsvariablen, die bei Bedarf angepasst werden können: 

- `FRONTEND_PORT`: Port unter dem das Frontend und die API auf dem Host erreichbar ist. Default ist `80`.
- `DATASOURCE_PROCESS_POOL_SIZE`: Anzahl der Worker-Prozesse im Backend, die zum Ausführen der Datenquellen genutzt werden. Default ist `2`. Je mehr Datenquellen parallel laufen können, desto höher sollte die Anzahl der Worker-Prozesse sein.
- `GLOBAL_ID_PATTERN`: Regulärer Ausdruck auf dessen Basis geprüft wird, ob es sich bei einer ID um eine globale ID handelt. Default ist `^[A-Za-z]+:[^:\s]+:[^:\s]+(?::[^:\s]*)*$` (entspricht dem Pattern der DHID, DTID, DFID).

(h-installation-additional-services)=

## Zusätzliche Dienste

EchoGTFS bietet zusätzliche Dienste, um Datenquellen bspw. über SIRI Publish/Subscribe anbinden zu können. Diese zusätzlichen Dienste werden **nicht automatisch mit gestartet**, sondern müssen beim Start über ein Profil aktiviert werden. Aktuell stehen folgende Profile zur Verfügung:

- `siripubsub`: SIRI-Kommunikationsdienst zum Betrieb mit SIRI Publish/Subscribe

### SIRI-Kommunikationsdienst

Der SIRI-Kommunikationsdienst ermöglich die Anbindung von Datenquellen mittels SIRI Publish/Subscribe Pattern. Der SIRI-Kommunikationsdienst bietet einen Endpunkt, über den Anfragen von SIRI-Producern entgegengenommen werden können. Er wird über das Profil `siripubsub` aktiviert und bietet folgende  zusätzlichen Umbebungsvariablen:

- `SIRI_PORT`: Port für die eingehenden Anfragen vom SIRI-Producer an den SIRI-Kommunikationsdienst. Default ist `8080`.
- `SIRI_STATUS_ENABLED`: Wenn auf `true` gesetzt, wird über den SIRI-Port unter der Adresse `/status` der aktuelle Status des SIRI-Kommunikationsdienstes angezeigt. Default ist `false`.

```{warning}
Die Statusanzeige des SIRI-Kommunikationsdienstes sollte in keinem Fall über das öffentliche Netzwerk erreichbar sein, sondern ggf. durch einen ReverseProxy auf das interne Netz beschränkt werden! Über die Statusanzeige und die damit einhergehenden Schnittstellen besteht auch die Möglichkeit, festgefahrende Abonnements manuell zu löschen.

**Die Pfade `/status` und `/api/...` müssen vor Zugriffen von außerhalb des Netzwerks geschützt werden.**
```

(h-installation-startup)=

## Start der Anwendung

Wenn soweit alle Konfigurationen vorgenommen sind, starten Sie EchoGTFS, indem Sie folgendes Kommando im Projektverzeichnis ausführen:

```shell
docker compose [--profile <profile1>, --profile <profile2>] up -d --build
```

Die Angabe von Profilen ist dabei optional und dient dem Start zusätzlicher Dienste.

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
