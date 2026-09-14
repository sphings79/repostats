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
        "repo.views": "Aufrufe",
        "repo.clones": "Clones",
        "repo.stars": "Sterne im Verlauf",
        "repo.installs": "Installationen",
        "repo.referrers": "Herkunft der Besucher",
        "repo.paths": "Meistbesuchte Seiten",
        "repo.assets": "Release-Downloads",
        "repo.created": "angelegt",
        "repo.pushed": "zuletzt aktiv",

        "settings.title": "Verwaltung",
        "settings.sub": "Auswählen, welche Repositories verfolgt werden. Nur diese werden abgefragt und gespeichert.",
        "settings.no_token": "Kein <code>GITHUB_TOKEN</code> gesetzt — ohne Token bleiben Aufrufe und Clones leer.",
        "settings.refresh": "Repository-Liste aktualisieren",
        "settings.collect_full": "Jetzt alles sammeln",
        "settings.collect_quick": "Nur Zähler aktualisieren",
        "settings.running": "läuft gerade",
        "settings.filter": "Filtern …",
        "settings.all": "Alle",
        "settings.none": "Keine",
        "settings.own": "Nur eigene",
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
        "run.running": "läuft",
        "footer.last_run": "Letzter Lauf",
        "footer.ok": "erfolgreich",
        "footer.failed": "mit Fehlern",
        "footer.collecting": "Sammlung läuft …",

        "ago.now": "gerade eben",
        "ago.minutes": "vor {n} min",
        "ago.hours": "vor {n} h",
        "ago.days": "vor {n} d",
        "ago.never": "—",
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
        "repo.views": "Views",
        "repo.clones": "Clones",
        "repo.stars": "Stars over time",
        "repo.installs": "Installations",
        "repo.referrers": "Where visitors come from",
        "repo.paths": "Most visited pages",
        "repo.assets": "Release downloads",
        "repo.created": "created",
        "repo.pushed": "last active",

        "settings.title": "Settings",
        "settings.sub": "Pick the repositories to follow. Only these are queried and stored.",
        "settings.no_token": "No <code>GITHUB_TOKEN</code> set — without one, views and clones stay empty.",
        "settings.refresh": "Refresh repository list",
        "settings.collect_full": "Collect everything now",
        "settings.collect_quick": "Refresh counters only",
        "settings.running": "running",
        "settings.filter": "Filter …",
        "settings.all": "All",
        "settings.none": "None",
        "settings.own": "Own only",
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
        "run.running": "running",
        "footer.last_run": "Last run",
        "footer.ok": "succeeded",
        "footer.failed": "with errors",
        "footer.collecting": "collecting …",

        "ago.now": "just now",
        "ago.minutes": "{n} min ago",
        "ago.hours": "{n} h ago",
        "ago.days": "{n} d ago",
        "ago.never": "—",
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


def day_label(day: str, lang: str) -> str:
    try:
        moment = datetime.fromisoformat(day)
    except ValueError:
        return day
    return moment.strftime("%d.%m." if lang == "de" else "%b %-d")
