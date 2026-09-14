# Repo Stats

*[English version](README.md)*

Ein kleines, selbst gehostetes Dashboard für alles, was GitHub über die eigenen
Repositories weiß — und für die Zahlen, die es nach zwei Wochen wegwirft.

GitHub zeigt den Verkehr pro Repository, für vierzehn Tage, ein Repository nach
dem anderen. Es gibt keine Übersicht über mehrere, keine Historie und nirgends
eine Download-Zahl. Hier landet alles in einer SQLite-Datei und wird gezeichnet.

## Was drin steht

**Pro Konto:** Sterne, Forks, Beobachter, offene Issues, Release-Downloads,
Aufrufe und Clones über alle verfolgten Repositories, woher die Besucher kommen,
und wie sich das über die Zeit bewegt.

**Pro Repository:** dieselben Zahlen im Detail, dazu Mitwirkende, Commits,
offene und gemergte Pull Requests, Erfolgsquote und Dauer der CI-Läufe, die
meistbesuchten Seiten, die offenen Issues samt Links, Downloads je
Release-Datei — und eine Sterne-Kurve, die bis zum ersten Stern zurückreicht.
Die wird aus den Zeitstempeln der einzelnen Stargazer rekonstruiert, steht also
schon nach dem ersten Lauf zur Verfügung, statt bei null anzufangen.

**Für Home-Assistant-Integrationen** kommt die Installationszahl von
`analytics.home-assistant.io` dazu. Das ist die einzige Zahl hier, die zählt,
wer etwas tatsächlich benutzt — und nicht, wer es sich angesehen hat.

## Warum gesammelt werden muss

Aufruf- und Clone-Zahlen sieht nur der Eigentümer des Repositories, sie brauchen
also ein Token — deshalb läuft das serverseitig und nicht im Browser. Und GitHub
löscht sie nach vierzehn Tagen: Was bis dahin nicht gesichert ist, ist endgültig
weg. Ein Lauf am Tag genügt, denn jeder Lauf liefert das komplette
Vierzehn-Tage-Fenster — Ausfälle unter zwei Wochen heilen sich damit von selbst.

## Betrieb

```bash
cp .env.example .env    # Token und Konto eintragen
docker compose up -d
```

Dann `http://<host>:8377` öffnen, unter *Verwaltung* die Repositories auswählen
und *Jetzt alles sammeln* drücken.

Das Token braucht den Scope `repo` (klassisch) oder Lesezugriff auf Actions,
Administration, Contents, Issues, Metadata und Pull requests (fein granuliert).
Ohne Token funktioniert alles außer den Verkehrszahlen — die bleiben leer.

Für die rückwirkende Sternhistorie braucht es `GITHUB_TOKEN_STARS`: GitHub weist
fein granulierte Tokens am Stargazer-Endpunkt ab, über REST wie über GraphQL,
und anonym gibt es dort auch nichts. Nötig ist ein klassisches Token mit dem
Scope `public_repo`. Getrennt gehalten heißt: Das Haupttoken braucht nirgends
Schreibrechte. Ohne das Token beginnt die Sternkurve beim ersten Sammellauf.

`AUTH_PASSWORD` sollte gesetzt sein, außer es läuft kurz auf dem eigenen
Rechner: Hier stehen die privaten Repositories, und im Container liegt ein
Token, das sie alle lesen kann.

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `GITHUB_TOKEN` | — | Persönliches Zugriffstoken, erforderlich |
| `GITHUB_LOGIN` | — | Das Konto, das gesammelt wird, erforderlich |
| `GITHUB_TOKEN_STARS` | — | Klassisches Token mit `public_repo`, für die Sternhistorie |
| `AUTH_USER` | `admin` | Benutzer für die Anmeldung |
| `AUTH_PASSWORD` | — | Passwort; leer schaltet die Anmeldung ab |
| `PORT` | `8377` | Port auf dem Host |
| `FULL_RUN_HOUR` | `4` | Stunde (UTC) des täglichen Komplettlaufs |
| `QUICK_RUN_MINUTES` | `60` | Wie oft die günstigen Zähler aktualisiert werden |

Die Daten liegen im Volume `repostats-data` als eine SQLite-Datei — ein Backup
ist also eine Dateikopie.

## Hinweise

- Die Oberfläche spricht Deutsch und Englisch, der Umschalter sitzt oben rechts.
- Code und Kommentare sind auf Englisch.
- Nichts verlässt das eigene Netz. Nach außen gehen nur Anfragen an die
  GitHub-API und an die Home-Assistant-Statistik.
- Das Dashboard hat eine eigene Anmeldung. Hinter einem Reverse Proxy
  zusätzlich aufs eigene Netz beschränken — `docs/traefik.yaml.example` zeigt
  beide Schlösser zusammen, und `compose.override.yaml.example` hängt den
  Container ins Proxy-Netz, ohne einen Port zu veröffentlichen.

## Lizenz

MIT
