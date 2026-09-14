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
offene und gemergte Pull Requests, die meistbesuchten Seiten, Downloads je
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

Das Token braucht den Scope `repo` (klassisch) oder Lesezugriff auf
Administration, Contents, Issues, Metadata und Pull requests (fein granuliert).
Ohne Token funktioniert alles außer den Verkehrszahlen — die bleiben leer.

| Variable | Vorgabe | Bedeutung |
|---|---|---|
| `GITHUB_TOKEN` | — | Persönliches Zugriffstoken, erforderlich |
| `GITHUB_LOGIN` | — | Das Konto, das gesammelt wird, erforderlich |
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
- Es gibt keine Anmeldung. Im eigenen Netz betreiben oder hinter einen Proxy
  setzen, der das übernimmt.

## Lizenz

MIT
