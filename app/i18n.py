"""Two languages, picked from a cookie or the browser's preference.

Keys read like the English sentence they produce, so a missing translation
still shows something sensible rather than an identifier.
"""
from datetime import datetime, timezone

LANGUAGES = {"de": "Deutsch", "en": "English"}
DEFAULT = "de"

TEXTS: dict[str, dict[str, str]] = {
    "de": {
        "nav.overview": "Übersicht",
        "nav.settings": "Verwaltung",

        "overview.title": "Alle Repositories auf einen Blick",
        "overview.sub": "{n} beobachtet · Zahlen werden stündlich geholt, der Verlauf täglich gesichert",
        "overview.traffic": "Verkehr über alle Repositories",
        "overview.growth": "Sterne und Downloads",
        "overview.referrers": "Woher die Besucher kommen",
        "overview.repos": "Repositories",
        "overview.none": "Noch keine Repositories ausgewählt — das geht in der",
        "overview.none.link": "Verwaltung",

        "kpi.stars": "Sterne",
        "kpi.forks": "Forks",
        "kpi.watchers": "Beobachter",
        "kpi.views14": "Aufrufe (14 T)",
        "kpi.clones14": "Clones (14 T)",
        "kpi.downloads": "Release-Downloads",
        "kpi.installs": "HA-Installationen",
        "kpi.issues": "Offene Issues",
        "kpi.uniques": "Eindeutige Besucher",
        "kpi.prs": "Offene PRs",
        "kpi.commits": "Commits",
        "kpi.contributors": "Mitwirkende",
        "kpi.releases": "Releases",
        "kpi.visitors": "Besucher (14 T)",
        "kpi.cloners": "Klonende (14 T)",
        "kpi.sub.views": "{n} Aufrufe",
        "kpi.sub.domain": "{n} auf der Domain",
        "kpi.sub.clones": "{n} Clones",

        "hint.stars": "Sterne über alle verfolgten Repositories.",
        "hint.forks": "Kopien, die jemand unter seinem eigenen Konto angelegt hat.",
        "hint.watchers": "Personen, die Benachrichtigungen zu den Repositories abonniert haben.",
        "hint.visitors": "Wie viele unterschiedliche Besucher GitHub an einem Tag gezählt hat, aufsummiert über vierzehn Tage. Darunter steht die Zahl der Seitenaufrufe — dieselbe Person, die mehrere Seiten ansieht, zählt dort mehrfach.",
        "hint.cloners": "Wie viele unterschiedliche Quellen geklont haben. Die Rohzahl darunter ist deutlich höher, weil jeder CI-Lauf mitzählt: Ein <code>actions/checkout</code> im Workflow ist für GitHub ein Clone, bei einem Matrix-Build entsprechend einer pro Job. Dazu kommen Bots und Spiegeldienste.",
        "hint.downloads": "Wie oft Dateien heruntergeladen wurden, die an ein Release angehängt sind. Der Quellcode-Tarball, den GitHub automatisch erzeugt, wird dabei nicht gezählt.",
        "hint.installs": "Home-Assistant-Instanzen, die diese Integration einsetzen und ihre Statistik eingeschaltet haben. Die einzige Zahl hier, die Nutzung zeigt statt Neugier — die tatsächliche Verbreitung liegt höher. In der Summe zählt jede Integration nur einmal, und Forks bleiben außen vor: Sie tragen die Domain des Projekts, aus dem sie stammen, und deren Nutzer gehören nicht hierher.",
        "hint.installs.fork": "Dieses Repository teilt sich die Integrations-Domain mit einem anderen Projekt. Gezählt werden nur Instanzen, die eine hier veröffentlichte Version einsetzen — die übrigen gehören zum anderen Projekt.",
        "installs.mine": "eigene Version",
        "installs.other": "andere Version",
        "installs.versions": "Nach Version",
        "installs.more": "und {n} weitere Versionen anderer Projekte",
        "installs.shared": "Diese Domain teilen sich mehrere Projekte: {total} Instanzen melden sie insgesamt, davon {mine} mit einer hier veröffentlichten Version.",
        "hint.issues": "Offene Issues, ohne Pull Requests. GitHub zählt die sonst mit.",
        "hint.prs": "Offene Pull Requests.",
        "hint.commits": "Commits auf dem Standard-Branch.",
        "hint.contributors": "Konten mit mindestens einem Commit.",
        "hint.releases": "Angelegte Releases, Entwürfe eingeschlossen.",
        "hint.ci": "Anteil erfolgreicher Workflow-Läufe unter den letzten hundert. Laufende zählen nicht mit.",
        "hint.ci_runs": "Abgeschlossene Workflow-Läufe unter den letzten hundert.",
        "hint.ci_time": "Durchschnittliche Dauer eines Laufs vom Start bis zum Ende.",
        "hint.repos": "Repositories, die verfolgt werden.",

        "kpi.ci": "CI-Erfolgsquote",
        "kpi.ci_runs": "CI-Läufe",
        "kpi.ci_time": "Ø CI-Dauer",
        "kpi.installs.long": "Home-Assistant-Installationen",
        "kpi.installs.note": "gemeldet von Instanzen mit aktivierter Statistik",

        "col.repo": "Repository",
        "col.issues": "Issues",
        "col.views": "Aufrufe",
        "col.clones": "Clones",
        "col.downloads": "Downloads",
        "col.30days": "30 Tage",
        "col.active": "Aktiv",
        "col.language": "Sprache",
        "col.kind": "Art",
        "col.last_active": "Zuletzt aktiv",
        "col.release": "Release",
        "col.file": "Datei",
        "col.published": "Veröffentlicht",
        "col.start": "Start",
        "col.result": "Ergebnis",
        "col.note": "Hinweis",
        "col.repos": "Repos",

        "repo.back": "← Übersicht",
        "repo.untrack": "Nicht mehr beobachten",
        "repo.track": "Wieder beobachten",
        "repo.untracked": "Dieses Repository wird nicht mehr abgefragt. Die bisher gesammelten Zahlen bleiben erhalten.",
        "repo.untrack.confirm": "{name} nicht mehr beobachten? Die gesammelten Zahlen bleiben erhalten.",
        "repo.views": "Aufrufe",
        "repo.clones": "Clones",
        "repo.stars": "Sterne im Verlauf",
        "repo.installs": "Installationen",
        "repo.referrers": "Herkunft der Besucher",
        "repo.paths": "Meistbesuchte Seiten",
        "repo.assets": "Release-Downloads",
        "repo.ci": "Workflow-Läufe",
        "chart.ci_runs": "Läufe",
        "chart.ci_failures": "Fehlschläge",
        "col.ci": "CI",
        "repo.created": "angelegt",
        "repo.pushed": "zuletzt aktiv",

        "settings.title": "Verwaltung",
        "settings.sub": "Auswählen, welche Repositories verfolgt werden. Nur diese werden abgefragt und gespeichert.",
        "settings.no_token": "Kein <code>GITHUB_TOKEN</code> gesetzt — ohne Token bleiben Aufrufe und Clones leer.",
        "settings.refresh": "Repository-Liste aktualisieren",
        "settings.collect_full": "Jetzt alles sammeln",
        "settings.collect_quick": "Nur Zähler aktualisieren",
        "settings.running": "läuft gerade",
        "settings.queued": "steht an",
        "settings.filter": "Nach Name oder Beschreibung suchen …",
        "settings.filters": "Filter",
        "settings.selection": "Schnellauswahl",
        "settings.check_visible": "Sichtbare ankreuzen",
        "settings.uncheck_visible": "Sichtbare abwählen",
        "settings.invert": "Umkehren",
        "settings.visible": "{shown} von {total} sichtbar",
        "settings.reset": "Filter zurücksetzen",

        "filter.kind": "Art",
        "filter.kind.any": "alle",
        "filter.kind.own": "eigene",
        "filter.kind.fork": "Forks",
        "filter.kind.private": "privat",
        "filter.kind.public": "öffentlich",
        "filter.kind.archived": "archiviert",
        "filter.kind.active": "nicht archiviert",
        "filter.lang": "Sprache",
        "filter.lang.any": "alle",
        "filter.state": "Haken",
        "filter.state.any": "alle",
        "filter.state.tracked": "nur ausgewählte",
        "filter.state.untracked": "nur nicht ausgewählte",
        "filter.ha": "Integration",
        "filter.ha.any": "alle",
        "filter.ha.yes": "Home Assistant",
        "filter.ha.no": "keine",
        "settings.display": "Anzeige",
        "settings.sticky": "Veränderung stehen lassen, bis sich etwas ändert",
        "settings.sticky.note": "Aus: Die Veränderung bezieht sich auf den letzten Seitenaufruf und steht nach einem Neuladen wieder auf ±0. An: Sie bleibt stehen, bis sich die Zahl wirklich wieder bewegt.",
        "settings.display.save": "Speichern",
        "settings.save": "Auswahl speichern",
        "settings.selected": "ausgewählt",
        "settings.runs": "Letzte Läufe",

        "tag.private": "privat",
        "tag.fork": "Fork",
        "tag.archived": "archiviert",

        "chart.views": "Aufrufe",
        "chart.views_unique": "Eindeutige Besucher",
        "chart.clones": "Clones",
        "chart.clones_unique": "Eindeutig",
        "chart.stars": "Sterne",
        "chart.downloads": "Downloads",
        "chart.installs": "Installationen",
        "chart.empty": "Noch keine Daten – der erste Lauf steht aus.",
        "bars.empty": "Keine Daten im 14-Tage-Fenster.",

        "run.ok": "ok",
        "run.failed": "Fehler",
        "run.interrupted": "abgebrochen",
        "run.running": "läuft",
        "footer.last_run": "Letzter Lauf",
        "footer.ok": "erfolgreich",
        "footer.failed": "mit Fehlern",
        "footer.interrupted": "abgebrochen",
        "footer.collecting": "Sammlung läuft …",
        "footer.source": "Quelltext (AGPL-3.0)",

        "top.share": "Verteilung",
        "top.across": "über {n} Repositories",
        "top.of_raw": "aus {n} roh",
        "top.assets": "Meistgeladene Dateien",

        "issues.title": "Offene Issues",
        "issues.sub": "{n} offen über alle verfolgten Repositories",
        "issues.none": "Nichts offen. Bemerkenswert.",
        "issues.opened": "geöffnet",
        "issues.updated": "zuletzt",
        "issues.comments": "Kommentare",
        "issues.stale": "seit über 90 Tagen unberührt",

        "login.title": "Anmeldung",
        "login.sub": "Dieses Dashboard ist geschützt.",
        "login.user": "Benutzer",
        "login.password": "Passwort",
        "login.submit": "Anmelden",
        "login.failed": "Benutzer oder Passwort stimmt nicht.",
        "login.logout": "Abmelden",

        "ago.now": "gerade eben",
        "ago.minutes": "vor {n} min",
        "ago.hours": "vor {n} h",
        "ago.days": "vor {n} d",
        "ago.never": "—",

        "since.now": "gerade eben",
        "since.minutes": "seit {n} min",
        "since.hours": "seit {n} h",
        "since.days": "seit {n} d",
        "since.date": "seit {date}",
    },
    "en": {
        "nav.overview": "Overview",
        "nav.settings": "Settings",

        "overview.title": "Every repository at a glance",
        "overview.sub": "{n} followed · counters refresh hourly, the history is kept daily",
        "overview.traffic": "Traffic across all repositories",
        "overview.growth": "Stars and downloads",
        "overview.referrers": "Where visitors come from",
        "overview.repos": "Repositories",
        "overview.none": "No repositories picked yet — that happens under",
        "overview.none.link": "Settings",

        "kpi.stars": "Stars",
        "kpi.forks": "Forks",
        "kpi.watchers": "Watchers",
        "kpi.views14": "Views (14 d)",
        "kpi.clones14": "Clones (14 d)",
        "kpi.downloads": "Release downloads",
        "kpi.installs": "HA installs",
        "kpi.issues": "Open issues",
        "kpi.uniques": "Unique visitors",
        "kpi.prs": "Open PRs",
        "kpi.commits": "Commits",
        "kpi.contributors": "Contributors",
        "kpi.releases": "Releases",
        "kpi.visitors": "Visitors (14 d)",
        "kpi.cloners": "Cloners (14 d)",
        "kpi.sub.views": "{n} views",
        "kpi.sub.domain": "{n} on the domain",
        "kpi.sub.clones": "{n} clones",

        "hint.stars": "Stars across every followed repository.",
        "hint.forks": "Copies somebody made under their own account.",
        "hint.watchers": "People subscribed to notifications for these repositories.",
        "hint.visitors": "How many distinct visitors GitHub counted on a day, added up over fourteen days. Below it are page views — one person looking at several pages counts several times there.",
        "hint.cloners": "How many distinct sources cloned. The raw number below is much higher because every CI run counts: an <code>actions/checkout</code> in a workflow is a clone to GitHub, one per job in a matrix build. Bots and mirroring services add to it.",
        "hint.downloads": "How often files attached to a release were downloaded. The source tarball GitHub generates on its own is not counted.",
        "hint.installs": "Home Assistant instances running this integration with analytics switched on. The only figure here that shows use rather than curiosity — actual adoption is higher. The total counts each integration once and leaves forks out: a fork carries the domain of the project it came from, and those users are not yours.",
        "hint.installs.fork": "This repository shares its integration domain with another project. Only instances running a version released here are counted — the rest belong to that other project.",
        "installs.mine": "released here",
        "installs.other": "another project",
        "installs.versions": "By version",
        "installs.more": "and {n} more versions from other projects",
        "installs.shared": "Several projects share this domain: {total} instances report it in total, {mine} of them on a version released here.",
        "hint.issues": "Open issues, without pull requests. GitHub otherwise counts those in.",
        "hint.prs": "Open pull requests.",
        "hint.commits": "Commits on the default branch.",
        "hint.contributors": "Accounts with at least one commit.",
        "hint.releases": "Releases created, drafts included.",
        "hint.ci": "Share of successful workflow runs among the last hundred. Runs in progress are left out.",
        "hint.ci_runs": "Finished workflow runs among the last hundred.",
        "hint.ci_time": "Average time a run takes from start to finish.",
        "hint.repos": "Repositories being followed.",

        "kpi.ci": "CI success rate",
        "kpi.ci_runs": "CI runs",
        "kpi.ci_time": "Avg CI time",
        "kpi.installs.long": "Home Assistant installations",
        "kpi.installs.note": "reported by instances with analytics enabled",

        "col.repo": "Repository",
        "col.issues": "Issues",
        "col.views": "Views",
        "col.clones": "Clones",
        "col.downloads": "Downloads",
        "col.30days": "30 days",
        "col.active": "Active",
        "col.language": "Language",
        "col.kind": "Kind",
        "col.last_active": "Last active",
        "col.release": "Release",
        "col.file": "File",
        "col.published": "Published",
        "col.start": "Started",
        "col.result": "Result",
        "col.note": "Note",
        "col.repos": "Repos",

        "repo.back": "← Overview",
        "repo.untrack": "Stop following",
        "repo.track": "Follow again",
        "repo.untracked": "This repository is no longer asked about. What was collected stays.",
        "repo.untrack.confirm": "Stop following {name}? The numbers collected so far are kept.",
        "repo.views": "Views",
        "repo.clones": "Clones",
        "repo.stars": "Stars over time",
        "repo.installs": "Installations",
        "repo.referrers": "Where visitors come from",
        "repo.paths": "Most visited pages",
        "repo.assets": "Release downloads",
        "repo.ci": "Workflow runs",
        "chart.ci_runs": "Runs",
        "chart.ci_failures": "Failures",
        "col.ci": "CI",
        "repo.created": "created",
        "repo.pushed": "last active",

        "settings.title": "Settings",
        "settings.sub": "Pick the repositories to follow. Only these are queried and stored.",
        "settings.no_token": "No <code>GITHUB_TOKEN</code> set — without one, views and clones stay empty.",
        "settings.refresh": "Refresh repository list",
        "settings.collect_full": "Collect everything now",
        "settings.collect_quick": "Refresh counters only",
        "settings.running": "running",
        "settings.queued": "queued",
        "settings.filter": "Search name or description …",
        "settings.filters": "Filters",
        "settings.selection": "Quick select",
        "settings.check_visible": "Tick the visible",
        "settings.uncheck_visible": "Untick the visible",
        "settings.invert": "Invert",
        "settings.visible": "{shown} of {total} shown",
        "settings.reset": "Clear filters",

        "filter.kind": "Kind",
        "filter.kind.any": "any",
        "filter.kind.own": "own",
        "filter.kind.fork": "forks",
        "filter.kind.private": "private",
        "filter.kind.public": "public",
        "filter.kind.archived": "archived",
        "filter.kind.active": "not archived",
        "filter.lang": "Language",
        "filter.lang.any": "any",
        "filter.state": "Ticked",
        "filter.state.any": "any",
        "filter.state.tracked": "only selected",
        "filter.state.untracked": "only unselected",
        "filter.ha": "Integration",
        "filter.ha.any": "any",
        "filter.ha.yes": "Home Assistant",
        "filter.ha.no": "none",
        "settings.display": "Display",
        "settings.sticky": "Keep a change on screen until the number moves again",
        "settings.sticky.note": "Off: the change is measured against your last visit, so a reload puts it back to ±0. On: it stays until the number really moves again.",
        "settings.display.save": "Save",
        "settings.save": "Save selection",
        "settings.selected": "selected",
        "settings.runs": "Recent runs",

        "tag.private": "private",
        "tag.fork": "fork",
        "tag.archived": "archived",

        "chart.views": "Views",
        "chart.views_unique": "Unique visitors",
        "chart.clones": "Clones",
        "chart.clones_unique": "Unique",
        "chart.stars": "Stars",
        "chart.downloads": "Downloads",
        "chart.installs": "Installations",
        "chart.empty": "No data yet — the first run is still to come.",
        "bars.empty": "Nothing in the fourteen-day window.",

        "run.ok": "ok",
        "run.failed": "failed",
        "run.interrupted": "interrupted",
        "run.running": "running",
        "footer.last_run": "Last run",
        "footer.ok": "succeeded",
        "footer.failed": "with errors",
        "footer.interrupted": "interrupted",
        "footer.collecting": "collecting …",
        "footer.source": "Source (AGPL-3.0)",

        "top.share": "How it splits up",
        "top.across": "across {n} repositories",
        "top.of_raw": "out of {n} raw",
        "top.assets": "Most downloaded files",

        "issues.title": "Open issues",
        "issues.sub": "{n} open across the followed repositories",
        "issues.none": "Nothing open. Remarkable.",
        "issues.opened": "opened",
        "issues.updated": "last touched",
        "issues.comments": "comments",
        "issues.stale": "untouched for over 90 days",

        "login.title": "Sign in",
        "login.sub": "This dashboard is protected.",
        "login.user": "User",
        "login.password": "Password",
        "login.submit": "Sign in",
        "login.failed": "That user or password is not right.",
        "login.logout": "Sign out",

        "ago.now": "just now",
        "ago.minutes": "{n} min ago",
        "ago.hours": "{n} h ago",
        "ago.days": "{n} d ago",
        "ago.never": "—",

        "since.now": "just now",
        "since.minutes": "{n} min ago",
        "since.hours": "{n} h ago",
        "since.days": "{n} d ago",
        "since.date": "since {date}",
    },
}


def pick(cookie: str | None, accept_language: str | None) -> str:
    """Cookie wins; otherwise take the first understood browser preference."""
    if cookie in LANGUAGES:
        return cookie
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGUAGES:
            return code
    return DEFAULT


def translator(lang: str):
    texts = TEXTS.get(lang, TEXTS[DEFAULT])
    fallback = TEXTS[DEFAULT]

    def t(key: str, **kwargs) -> str:
        value = texts.get(key) or fallback.get(key) or key
        return value.format(**kwargs) if kwargs else value

    return t


def number(value, lang: str) -> str:
    """1.234 in German, 1,234 in English."""
    text = f"{int(value or 0):,}"
    return text.replace(",", ".") if lang == "de" else text


def ago(value: str | None, lang: str) -> str:
    t = translator(lang)
    if not value:
        return t("ago.never")
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    minutes = int((datetime.now(timezone.utc) - moment).total_seconds() // 60)
    if minutes < 1:
        return t("ago.now")
    if minutes < 60:
        return t("ago.minutes", n=minutes)
    hours = minutes // 60
    if hours < 24:
        return t("ago.hours", n=hours)
    days = hours // 24
    if days < 30:
        return t("ago.days", n=days)
    return moment.strftime("%d.%m.%Y" if lang == "de" else "%b %-d, %Y")


def since(value: str | None, lang: str) -> str:
    """Like ago(), but read as a starting point: "seit 2 h", "2 h ago"."""
    t = translator(lang)
    if not value:
        return ""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    minutes = int((datetime.now(timezone.utc) - moment).total_seconds() // 60)
    if minutes < 1:
        return t("since.now")
    if minutes < 60:
        return t("since.minutes", n=minutes)
    hours = minutes // 60
    if hours < 24:
        return t("since.hours", n=hours)
    days = hours // 24
    if days < 30:
        return t("since.days", n=days)
    return t("since.date",
             date=moment.strftime("%d.%m.%Y" if lang == "de" else "%b %-d, %Y"))


def duration(seconds, lang: str) -> str:
    """Seconds below a minute, minutes below an hour, hours above."""
    if not seconds:
        return "—"
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    hours = seconds / 3600
    return f"{hours:.1f} h".replace(".", "," if lang == "de" else ".")


def day_label(day: str, lang: str) -> str:
    try:
        moment = datetime.fromisoformat(day)
    except ValueError:
        return day
    return moment.strftime("%d.%m." if lang == "de" else "%b %-d")
