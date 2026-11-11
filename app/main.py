"""The web application: one overview, one page per repository, one settings page.

Repo Stats — a self-hosted dashboard for GitHub repository statistics.
Copyright (C) 2026 sphings79

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version. It is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; see the licence for details. You should have received a
copy along with this program; if not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth as auth_module, charts, i18n, mqtt as mqtt_module, notify as notify_module
from .collector import Collector
from .db import Database

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_LOGGER = logging.getLogger("repostats")

BASE = Path(__file__).parent


def _asset_version() -> str:
    """Newest change among the static files.

    Appended to the stylesheet and script URLs so a browser that cached the
    old ones picks the new ones up after an update, without a hard reload.
    """
    newest = 0.0
    for path in (BASE / "static").glob("*"):
        newest = max(newest, path.stat().st_mtime)
    return str(int(newest))


ASSETS = _asset_version()

# The licence asks that people using this over a network can get at the
# source, so the footer links to it.
SOURCE_URL = os.getenv("SOURCE_URL", "https://github.com/sphings79/repostats")
TOKEN = os.getenv("GITHUB_TOKEN", "")
LOGIN = os.getenv("GITHUB_LOGIN", "")
# Optional: a classic token without any scope. Fine-grained tokens are refused
# on the stargazers endpoint, which is where the star history comes from.
STAR_TOKEN = os.getenv("GITHUB_TOKEN_STARS", "")
DB_PATH = os.getenv("DB_PATH", "/data/repostats.db")
FULL_HOUR = int(os.getenv("FULL_RUN_HOUR", "4"))
QUICK_MINUTES = int(os.getenv("QUICK_RUN_MINUTES", "60"))

db = Database(DB_PATH)
collector = Collector(db, TOKEN, LOGIN, STAR_TOKEN)
auth = auth_module.Auth(db)
publisher = mqtt_module.Publisher(db, lambda rows: _install_total(rows))
notifier = notify_module.Notifier(db, lambda: _hidden_topics())


async def _after_run() -> None:
    """MQTT first, so the notifications see how that went too."""
    await publisher.publish()
    await notifier.after_run()


collector.after_run = _after_run


async def _scheduler() -> None:
    """Hourly counters, one full run a day, and a full run on an empty database."""
    stale = db.close_stale_runs()
    if stale:
        _LOGGER.info("%s collection(s) had been interrupted by a restart", stale)
    await asyncio.sleep(5)
    if not TOKEN or not LOGIN:
        _LOGGER.error("GITHUB_TOKEN and GITHUB_LOGIN have to be set")
        return

    try:
        if not db.repos(tracked_only=False):
            found = await collector.discover()
            _LOGGER.info("Found %s repositories; pick the ones to follow under /settings", found)
        if db.repos(tracked_only=True) and not db.last_run():
            await collector.run("full")
    except Exception:                                   # noqa: BLE001
        _LOGGER.exception("Initial collection failed")

    last_full = None
    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.hour == FULL_HOUR and last_full != now.date():
                await collector.run("full")
                last_full = now.date()
            else:
                await collector.run("quick")
        except Exception:                               # noqa: BLE001
            _LOGGER.exception("Scheduled collection failed")
        await asyncio.sleep(QUICK_MINUTES * 60)


async def _issues_scheduler() -> None:
    """Fetch the open issues and pull requests on their own clock.

    The interval is read every minute, so changing it under /settings takes
    effect without a restart. A full run fetches them too and counts as one.
    """
    if not TOKEN or not LOGIN:
        return
    while True:
        await asyncio.sleep(60)
        try:
            minutes = int(db.setting(ISSUES_EVERY, "1440"))
            if minutes >= 1440 or collector.running or collector.pending:
                continue
            last = db.last_run_of(("issues", "full"))
            if last and (datetime.now(timezone.utc) - datetime.fromisoformat(last)
                         ).total_seconds() < minutes * 60:
                continue
            await collector.run("issues")
        except Exception:                               # noqa: BLE001
            _LOGGER.exception("Scheduled issue refresh failed")


async def _notify_retry() -> None:
    """Another go at messages that could not be delivered."""
    while True:
        await asyncio.sleep(60)
        try:
            await notifier.retry()
        except Exception:                               # noqa: BLE001
            _LOGGER.exception("Retrying notifications failed")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [asyncio.create_task(_scheduler()), asyncio.create_task(_issues_scheduler()),
             asyncio.create_task(_notify_retry())]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Repo Stats", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

OPEN_PATHS = ("/login", "/setup", "/health", "/static", "/lang")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Everything but the login page needs a valid session.

    Before the first account exists there is nothing to sign in to, so every
    visitor is sent to the setup page instead.
    """
    path = request.url.path
    if not path.startswith(OPEN_PATHS):
        if not auth.configured:
            return RedirectResponse("/setup", status_code=303)
        if not auth.valid(request.cookies.get(auth_module.COOKIE)):
            target = "/login"
            if path != "/":
                target += f"?next={path}"
            return RedirectResponse(target, status_code=303)
    return await call_next(request)
templates = Jinja2Templates(directory=BASE / "templates")


def _render(request: Request, name: str, context: dict):
    """Render with the language the visitor asked for."""
    lang = i18n.pick(request.cookies.get("lang"),
                     request.headers.get("accept-language"))
    context = {
        **context,
        "lang": lang,
        "languages": i18n.LANGUAGES,
        "t": i18n.translator(lang),
        "num": lambda v: i18n.number(v, lang),
        "ago": lambda v: i18n.ago(v, lang),
        "duration": lambda v: i18n.duration(v, lang),
        "auth_enabled": auth.configured,
        "min_password": auth_module.MIN_PASSWORD,
        "asset_version": ASSETS,
        "source_url": SOURCE_URL,
        "alert_run": _failed_run(),
        "alert_mqtt": _failed_mqtt(),
    }
    return templates.TemplateResponse(request, name, context)


@app.get("/", response_class=HTMLResponse)
async def overview(request: Request, days: int = 30):
    lang = i18n.pick(request.cookies.get("lang"), request.headers.get("accept-language"))
    t = i18n.translator(lang)
    repos = db.repos()
    snapshots = db.latest_snapshots()

    rows = []
    for repo in repos:
        snap = snapshots.get(repo["full_name"])
        rows.append({
            "repo": repo,
            "snap": snap,
            "views": _sum(db.series(repo["full_name"], "views", 14)),
            "clones": _sum(db.series(repo["full_name"], "clones", 14)),
            "views_unique": _sum(db.series(repo["full_name"], "views_unique", 14)),
            "clones_unique": _sum(db.series(repo["full_name"], "clones_unique", 14)),
            "spark": charts.sparkline(db.series(repo["full_name"], "views", 30), days=30),
        })
    rows.sort(key=lambda r: (r["snap"]["stars"] if r["snap"] else 0,
                             r["views"]), reverse=True)

    totals = {
        "repos": len(repos),
        **_tile_values(rows),
        "views": sum(r["views"] for r in rows),
        "clones": sum(r["clones"] for r in rows),
        "views_unique": sum(r["views_unique"] for r in rows),
        "clones_unique": sum(r["clones_unique"] for r in rows),
    }

    # Only once there is something to compare; before the first run every
    # tile would set its mark to zero and report a jump afterwards.
    deltas = _deltas(
        "overview", _tile_values(rows), lang,
        past=lambda moment: _overview_at(repos, moment),
    ) if snapshots else {}
    changes = _repo_changes(deltas, snapshots, lang, CHANGE_COLUMNS)

    traffic = charts.area_chart([
        {"label": t("chart.views"), "rows": db.totals_series("views", days),
         "colour": "var(--accent)"},
        {"label": t("chart.clones"), "rows": db.totals_series("clones", days),
         "colour": "var(--accent-2)"},
    ], days=days, lang=lang)
    growth = charts.area_chart([
        {"label": t("chart.stars"),
         "rows": _carried_total(repos, "stars_total", days)
                 or db.snapshot_series("stars", days),
         "colour": "var(--gold)", "carry": True},
        {"label": t("chart.downloads"), "rows": db.snapshot_series("downloads", days),
         "colour": "var(--violet)", "carry": True},
    ], days=days, lang=lang)

    return _render(request, "index.html", {
        "rows": rows, "totals": totals, "traffic": traffic, "growth": growth,
        "referrers": charts.bars(db.top_referrers(), "source", "views", lang=lang),
        "days": days, "last_run": db.last_run(), "running": collector.running,
        "deltas": deltas, "changes": changes,
    })


@app.get("/repo/{owner}/{name}", response_class=HTMLResponse)
async def repo_page(request: Request, owner: str, name: str, days: int = 30):
    lang = i18n.pick(request.cookies.get("lang"), request.headers.get("accept-language"))
    t = i18n.translator(lang)
    full_name = f"{owner}/{name}"
    repo = db.repo(full_name)
    if repo is None:
        return RedirectResponse("/", status_code=303)

    snap = db.latest_snapshot(full_name)
    traffic = charts.area_chart([
        {"label": t("chart.views"), "rows": db.series(full_name, "views", days),
         "colour": "var(--accent)"},
        {"label": t("chart.views_unique"), "rows": db.series(full_name, "views_unique", days),
         "colour": "var(--accent-2)"},
    ], days=days, lang=lang)
    clones = charts.area_chart([
        {"label": t("chart.clones"), "rows": db.series(full_name, "clones", days),
         "colour": "var(--accent-2)"},
        {"label": t("chart.clones_unique"), "rows": db.series(full_name, "clones_unique", days),
         "colour": "var(--violet)"},
    ], days=days, lang=lang)
    star_rows = db.series(full_name, "stars_total", days)
    if not star_rows:
        # No reconstructed history — draw what the daily runs have recorded.
        star_rows = db.repo_snapshot_series(full_name, "stars", days)
    stars = charts.area_chart([
        {"label": t("chart.stars"), "rows": star_rows,
         "colour": "var(--gold)", "carry": True},
    ], days=days, lang=lang)
    ci = None
    if snap and snap["ci_runs"]:
        ci = charts.area_chart([
            {"label": t("chart.ci_runs"), "rows": db.series(full_name, "ci_runs", days),
             "colour": "var(--accent)"},
            {"label": t("chart.ci_failures"), "rows": db.series(full_name, "ci_failures", days),
             "colour": "var(--gold)"},
        ], days=days, lang=lang)

    # Every version of ours, and only the largest few of the others: a busy
    # domain reports dozens, and the point is the comparison, not the list.
    versions = []
    if repo["ha_domain"]:
        rows = db.ha_versions(full_name)
        mine = [r for r in rows if r["mine"]]
        others = [r for r in rows if not r["mine"]]
        versions = mine + others[:5]
        hidden_versions = max(len(others) - 5, 0)
    else:
        hidden_versions = 0
    installs = None
    if repo["ha_domain"]:
        installs = charts.area_chart([
            {"label": t("chart.installs"), "rows": db.series(full_name, "ha_installs", days),
             "colour": "var(--accent-2)", "carry": True},
        ], days=days, lang=lang)

    deltas = _deltas(
        full_name, _repo_values(snap), lang,
        past=lambda moment: _repo_at(full_name, moment),
    ) if snap else {}
    assets = db.assets(full_name)

    return _render(request, "repo.html", {
        "repo": repo, "snap": snap, "days": days, "deltas": deltas,
        "traffic": traffic, "clones": clones, "stars": stars, "installs": installs,
        "ci": ci, "versions": versions, "hidden_versions": hidden_versions,
        "referrers": charts.bars(db.referrers(full_name), "source", "views", lang=lang),
        "paths": charts.bars(db.paths(full_name), "path", "views", lang=lang),
        "assets": assets,
        "asset_changes": _asset_changes(assets, deltas, lang),
        "pulls": db.pulls(full_name),
        "views14": _sum(db.series(full_name, "views", 14)),
        "clones14": _sum(db.series(full_name, "clones", 14)),
        "uniques14": _sum(db.series(full_name, "views_unique", 14)),
        "clone_uniques14": _sum(db.series(full_name, "clones_unique", 14)),
    })


# Which repository column or daily metric sits behind each tile.
BREAKDOWN = {
    "stars":     {"column": "stars",     "title": "kpi.stars", "delta": True},
    "forks":     {"column": "forks",     "title": "kpi.forks", "delta": True},
    "watchers":  {"column": "watchers",  "title": "kpi.watchers", "delta": True},
    "downloads": {"column": "downloads", "title": "kpi.downloads", "delta": True},
    "installs":  {"column": "ha_installs", "title": "kpi.installs.long", "delta": True},
    "views":     {"daily": "views", "unique": "views_unique", "title": "kpi.visitors"},
    "clones":    {"daily": "clones", "unique": "clones_unique", "title": "kpi.cloners"},
}


@app.get("/top/{metric}", response_class=HTMLResponse)
async def breakdown(request: Request, metric: str, days: int = 14):
    """Which repositories a number on the overview is made of."""
    spec = BREAKDOWN.get(metric)
    if spec is None:
        return RedirectResponse("/", status_code=303)

    lang = i18n.pick(request.cookies.get("lang"), request.headers.get("accept-language"))
    t = i18n.translator(lang)
    repos = db.repos()
    snapshots = db.latest_snapshots()

    rows = []
    for repo in repos:
        snap = snapshots.get(repo["full_name"])
        if "daily" in spec:
            value = _sum(db.series(repo["full_name"], spec["daily"], days))
            second = _sum(db.series(repo["full_name"], spec["unique"], days))
            value, second = second, value          # lead with the distinct count
        else:
            value = (snap[spec["column"]] if snap else 0) or 0
            second = None
        if value:
            rows.append({"repo": repo, "value": value, "second": second,
                         "snap": snap})

    rows.sort(key=lambda r: r["value"], reverse=True)
    total = sum(r["value"] for r in rows)
    second_total = sum(r["second"] or 0 for r in rows) if "daily" in spec else None

    # installations are per integration, and a fork carries a foreign domain
    note = None
    if metric == "installs":
        note = t("hint.installs")
        seen = set()
        for row in rows:
            domain = row["repo"]["ha_domain"]
            row["muted"] = bool(row["repo"]["fork"]) or domain in seen
            if domain:
                seen.add(domain)
        total = sum(r["value"] for r in rows if not r["muted"])

    # The same change the tile on the overview shows, measured against the
    # same mark. The overview counts every followed repository, so the
    # number compared is that total, not the narrowed one listed here.
    delta, changes, asset_changes = None, {}, None
    if spec.get("delta") and snapshots:
        everyone = [{"repo": r, "snap": snapshots.get(r["full_name"])} for r in repos]
        deltas = _deltas("overview", _tile_values(everyone), lang, commit=False,
                         past=lambda moment: _overview_at(repos, moment))
        delta = deltas.get(metric)
        changes = _repo_changes(deltas, snapshots, lang, [metric])
        if metric == "downloads":
            asset_changes = _asset_changes(db.assets(None), deltas, lang)

    return _render(request, "top.html", {
        "metric": metric, "rows": rows, "total": total, "delta": delta,
        "changes": changes, "asset_changes": asset_changes,
        "second_total": second_total, "days": days,
        "title": t(spec["title"]), "note": note,
        "assets": db.assets(None) if metric == "downloads" else None,
        "last_run": db.last_run(),
    })


def _hidden_topics() -> set[str]:
    return {t for t in db.setting(HIDDEN, "").split(",") if t}


def _topic_scope(rows, topic: str, everything: bool):
    """Narrow a list of issues or pull requests by repository topic.

    A repository carrying any hidden topic drops out, even if it has other,
    visible ones, unless everything is asked for. Returns the remaining rows,
    how many repositories were hidden, and the topics left to pick from.
    """
    topics = {r["full_name"]: {t for t in (r["topics"] or "").split(",") if t}
              for r in db.repos()}
    hidden = _hidden_topics()
    dropped: set[str] = set()
    kept = []
    for row in rows:
        mine = topics.get(row["full_name"], set())
        if hidden and not everything and mine & hidden:
            dropped.add(row["full_name"])
            continue
        kept.append(row)
    choices = sorted({t for row in kept for t in topics.get(row["full_name"], set())}
                     - (set() if everything else hidden))
    if topic:
        kept = [r for r in kept if topic in topics.get(r["full_name"], set())]
    return kept, len(dropped), choices


def _list_total_delta(metric: str, lang: str, filtered: bool):
    """The change of the open total, only while the list is that total."""
    if filtered:
        return None
    repos = db.repos()
    snapshots = db.latest_snapshots()
    if not snapshots:
        return None
    rows = [{"repo": r, "snap": snapshots.get(r["full_name"])} for r in repos]
    return _deltas("overview", _tile_values(rows), lang, commit=False,
                   past=lambda moment: _overview_at(repos, moment)).get(metric)


@app.get("/issues", response_class=HTMLResponse)
async def issues(request: Request, repo: str | None = None,
                 topic: str = "", all: int = 0):
    """Every open issue across the followed repositories, with links."""
    lang = i18n.pick(request.cookies.get("lang"), request.headers.get("accept-language"))
    rows, hidden, choices = _topic_scope(db.issues(repo), topic, bool(all))
    per_repo: dict[str, list] = {}
    for row in rows:
        per_repo.setdefault(row["full_name"], []).append(row)

    return _render(request, "issues.html", {
        "groups": sorted(per_repo.items(), key=lambda kv: (-len(kv[1]), kv[0])),
        "total": len(rows),
        "single": repo, "topic": topic, "choices": choices,
        "hidden_repos": hidden, "show_all": bool(all), "has_hidden": bool(_hidden_topics()),
        "delta": _list_total_delta("issues", lang, bool(repo or topic or hidden)),
        "last_run": db.last_run(),
    })


@app.get("/pulls", response_class=HTMLResponse)
async def pulls(request: Request, repo: str | None = None, bots: int = 1,
                topic: str = "", all: int = 0):
    """Every open pull request across the followed repositories, with links."""
    lang = i18n.pick(request.cookies.get("lang"), request.headers.get("accept-language"))
    rows, hidden, choices = _topic_scope(db.pulls(repo), topic, bool(all))
    bot_count = sum(1 for r in rows if r["is_bot"])
    if not bots:
        rows = [r for r in rows if not r["is_bot"]]
    per_repo: dict[str, list] = {}
    for row in rows:
        per_repo.setdefault(row["full_name"], []).append(row)

    return _render(request, "pulls.html", {
        "groups": sorted(per_repo.items(), key=lambda kv: (-len(kv[1]), kv[0])),
        "total": len(rows),
        "bots": bot_count,
        "show_bots": bool(bots),
        "single": repo, "topic": topic, "choices": choices,
        "hidden_repos": hidden, "show_all": bool(all), "has_hidden": bool(_hidden_topics()),
        "delta": _list_total_delta("prs", lang, bool(repo or topic or hidden or not bots)),
        "last_run": db.last_run(),
    })


@app.post("/repo/{owner}/{name}/tracked")
async def set_tracked(owner: str, name: str, tracked: str = Form("0")):
    """Stop following a repository from its own page, or pick it up again.

    The collected numbers stay in the database — this only decides whether it
    is asked about from now on.
    """
    full_name = f"{owner}/{name}"
    follow = tracked == "1"
    db.set_tracked_one(full_name, follow)
    _LOGGER.info("%s is %s followed", full_name, "now" if follow else "no longer")
    return RedirectResponse(f"/repo/{full_name}" if follow else "/", status_code=303)


def _settings_context(mqtt_config: dict | None = None, mqtt_test: str | None = None) -> dict:
    repos = db.repos(tracked_only=False)
    topics = sorted({t for r in repos for t in (r["topics"] or "").split(",") if t})
    config = mqtt_config or mqtt_module.read_config(db)
    return {
        "repos": repos,
        "topics": topics,
        "runs": db.runs(),
        "running": collector.running,
        "pending": collector.pending,
        "login": LOGIN,
        "has_token": bool(TOKEN),
        "sticky": db.setting(STICKY, "1") == "1",
        "issues_minutes": int(db.setting(ISSUES_EVERY, "1440")),
        "issues_choices": ISSUES_CHOICES,
        "delta_show": db.setting(SHOW, "1") == "1",
        "delta_mode": db.setting(MODE, "visit"),
        "delta_modes": MODES,
        "hidden_topics": sorted(_hidden_topics()),
        # the password never goes back to the browser, only whether one is set
        "mqtt": {**config, "password": "", "has_password": bool(config["password"])},
        "mqtt_status": publisher.status(),
        "mqtt_test": mqtt_test,
    }


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return _render(request, "settings.html", _settings_context())


@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    db.set_tracked(form.getlist("tracked"))
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/collection")
async def save_collection(minutes: int = Form(1440)):
    db.set_setting(ISSUES_EVERY, str(minutes if minutes in ISSUES_CHOICES else 1440))
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/display")
async def save_display(request: Request):
    """Its own form: the one below it carries the tracked repositories, and
    posting that without them would clear every tick."""
    form = await request.form()
    db.set_setting(STICKY, "1" if form.get("sticky") else "0")
    db.set_setting(SHOW, "1" if form.get("show") else "0")
    mode = str(form.get("mode") or "visit")
    db.set_setting(MODE, mode if mode in MODES else "visit")
    # topics come from the page's own list; commas would break the storage
    hidden = sorted({str(t).strip() for t in form.getlist("hidden_topics")
                     if str(t).strip() and "," not in str(t)})
    db.set_setting(HIDDEN, ",".join(hidden))
    return RedirectResponse("/settings", status_code=303)


def _mqtt_from_form(form) -> tuple[dict, str | None]:
    """The broker settings as submitted, and what is wrong with them.

    A blank password keeps the stored one; there is no way to read it back
    out of the form, so blank cannot mean "none".
    """
    stored = mqtt_module.read_config(db)
    config = {
        "enabled": "1" if form.get("enabled") else "0",
        "host": str(form.get("host", "")).strip(),
        "port": str(form.get("port", "")).strip(),
        "user": str(form.get("user", "")).strip(),
        "password": str(form.get("password", "")) or stored["password"],
        "base": str(form.get("base", "")).strip().strip("/"),
        "prefix": str(form.get("prefix", "")).strip().strip("/"),
        "tls": "1" if form.get("tls") else "0",
        "tls_verify": "1" if form.get("tls_verify") else "0",
    }
    if form.get("clear_password"):
        config["password"] = ""

    problem = None
    if not config["host"]:
        problem = "mqtt.error.host"
    elif not (config["port"].isdigit() and 0 < int(config["port"]) < 65536):
        problem = "mqtt.error.port"
    elif not config["base"] or not config["prefix"] or any(
            c in config["base"] + config["prefix"] for c in "+#"):
        problem = "mqtt.error.topic"
    return config, problem


@app.post("/settings/mqtt")
async def save_mqtt(request: Request):
    config, problem = _mqtt_from_form(await request.form())
    if problem:
        return _render(request, "settings.html",
                       _settings_context(config, mqtt_test="!" + problem))
    for key, value in config.items():
        db.set_setting(f"mqtt_{key}", value)
    # an earlier verdict says nothing about the new settings
    db.set_setting("mqtt_ok", "")
    if config["enabled"] == "1":
        asyncio.create_task(publisher.publish())
    return RedirectResponse("/settings#mqtt", status_code=303)


@app.post("/settings/mqtt/test")
async def test_mqtt(request: Request):
    config, problem = _mqtt_from_form(await request.form())
    error = "!" + problem if problem else await publisher.test(config)
    return _render(request, "settings.html", _settings_context(config, mqtt_test=error))


@app.post("/discover")
async def discover():
    found = await collector.discover()
    _LOGGER.info("Repository list refreshed: %s entries", found)
    return RedirectResponse("/settings", status_code=303)


def _notify_context(test: dict | None = None, error: str | None = None,
                    config: dict | None = None) -> dict:
    status = notifier.status()
    iso = lambda stamp: (datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")
                         if stamp else None)
    status["last_sent"] = iso(status["last_sent"])
    if status["last_error"]:
        status["last_error"] = {**status["last_error"], "at": iso(status["last_error"]["ts"])}
    return {"cfg": config or notifier.config(), "flags": notifier.flags(),
            "status": status, "test": test, "error": error,
            "channels": notify_module.CHANNELS}


@app.get("/notifications", response_class=HTMLResponse)
async def notifications(request: Request):
    return _render(request, "notifications.html", _notify_context())


@app.post("/notifications", response_class=HTMLResponse)
async def save_notifications(request: Request):
    """Save, and optionally test one channel with what was just saved."""
    form = await request.form()
    get = lambda name: str(form.get(name) or "").strip()
    flag = lambda name: form.get(name) is not None
    old = notifier.config()

    try:
        priority = int(get("pushover_priority") or 0)
    except ValueError:
        priority = 0
    config = notify_module.normalise({
        "enabled": flag("enabled"), "lang": get("lang"),
        "telegram": {"enabled": flag("telegram_on"), "chat_id": get("telegram_chat")},
        "ha": {"enabled": flag("ha_on"), "url": get("ha_url"), "service": get("ha_service"),
               "insecure": flag("ha_insecure")},
        "pushover": {"enabled": flag("pushover_on"), "priority": priority},
        "webhook": {"enabled": flag("webhook_on"), "format": get("webhook_format"),
                    "insecure": flag("webhook_insecure")},
        "rules": {key: flag(f"rule_{key}") for key in old["rules"]},
    })
    # switching a channel on switches the whole thing on
    if any(config[ch]["enabled"] and not old[ch]["enabled"] for ch in notify_module.CHANNELS):
        config["enabled"] = True

    problem = notify_module.validate(config)
    secrets = notifier.secrets()
    for name, check in (("telegram_token", notify_module.TOKEN_RE),
                        ("ha_token", None), ("pushover_token", None),
                        ("pushover_user", None), ("webhook_auth", None),
                        ("webhook_url", notify_module.URL_RE)):
        value = get(name)
        if not value:
            continue
        if check and not check.match(value):
            problem = problem or ("badToken" if name == "telegram_token" else "badUrl")
        else:
            secrets[name] = value[:500]
    for channel in form.getlist("clear"):
        for name in notify_module.SECRETS_OF.get(str(channel), ()):
            secrets[name] = ""

    if problem:
        return _render(request, "notifications.html", _notify_context(
            error=problem, config=config))

    notifier.save_config(config)
    notifier.save_secrets(secrets)

    action = get("action")
    if action.startswith("test:"):
        result = await notifier.test(action[5:])
        return _render(request, "notifications.html", _notify_context(
            test={"channel": action[5:], **result}))
    return RedirectResponse("/notifications", status_code=303)


@app.post("/collect")
async def collect(kind: str = Form("full")):
    asyncio.create_task(collector.run("quick" if kind == "quick" else "full"))
    return RedirectResponse("/settings", status_code=303)


@app.get("/setup", response_class=HTMLResponse)
async def setup_form(request: Request):
    """The first account. Reachable only while there is none."""
    if auth.configured:
        return RedirectResponse("/login", status_code=303)
    return _render(request, "setup.html", {"name": "", "error": None})


@app.post("/setup")
async def setup(request: Request, user: str = Form(""), password: str = Form(""),
                repeat: str = Form("")):
    if auth.configured:
        return RedirectResponse("/login", status_code=303)
    error = auth_module.problem(user, password, repeat)
    if error:
        return _render(request, "setup.html", {"name": user, "error": error})

    auth.create(user, password)
    _LOGGER.info("Account created; the dashboard is closed to everyone else now")
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(auth_module.COOKIE, auth.issue(), max_age=auth_module.MAX_AGE,
                        httponly=True, samesite="lax")
    return response


@app.get("/account", response_class=HTMLResponse)
async def account_page(request: Request, done: str = ""):
    return _render(request, "account.html",
                   {"name": auth.user, "done": done, "name_error": None,
                    "password_error": None})


@app.post("/account/name")
async def change_name(request: Request, user: str = Form(""), current: str = Form("")):
    client = request.client.host if request.client else "?"
    error = None
    if not auth.verify(current, client):
        error = "account.error.current"
    elif not user.strip():
        error = "account.error.name"
    if error:
        return _render(request, "account.html",
                       {"name": auth.user, "done": "", "name_error": error,
                        "password_error": None})

    auth.set_name(user)
    # The old name was part of the signature, so this session needs a new
    # cookie right away — otherwise renaming would sign you out.
    response = RedirectResponse("/account?done=name", status_code=303)
    response.set_cookie(auth_module.COOKIE, auth.issue(), max_age=auth_module.MAX_AGE,
                        httponly=True, samesite="lax")
    return response


@app.post("/account/password")
async def change_password(request: Request, current: str = Form(""),
                          password: str = Form(""), repeat: str = Form(""),
                          others: str = Form("")):
    client = request.client.host if request.client else "?"
    error = None
    if not auth.verify(current, client):
        error = "account.error.current"
    else:
        error = auth_module.problem(auth.user, password, repeat)
    if error:
        return _render(request, "account.html",
                       {"name": auth.user, "done": "", "name_error": None,
                        "password_error": error})

    auth.set_password(password)
    if others:
        auth.rotate_key()
    response = RedirectResponse("/account?done=password", status_code=303)
    response.set_cookie(auth_module.COOKIE, auth.issue(), max_age=auth_module.MAX_AGE,
                        httponly=True, samesite="lax")
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/"):
    if not auth.configured:
        return RedirectResponse("/setup", status_code=303)
    if auth.valid(request.cookies.get(auth_module.COOKIE)):
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", {"next": next, "failed": False})


@app.post("/login")
async def login(request: Request, user: str = Form(""), password: str = Form(""),
                next: str = Form("/")):
    if not auth.configured:
        return RedirectResponse("/setup", status_code=303)
    client = request.client.host if request.client else "?"
    if not auth.check(user, password, client):
        _LOGGER.warning("Failed login from %s", client)
        return _render(request, "login.html", {"next": next, "failed": True})

    target = next if next.startswith("/") and not next.startswith("//") else "/"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(auth_module.COOKIE, auth.issue(), max_age=auth_module.MAX_AGE,
                        httponly=True, samesite="lax")
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth_module.COOKIE)
    return response


@app.get("/lang/{code}")
async def set_language(code: str, request: Request):
    """Remember a language choice for a year."""
    target = request.headers.get("referer", "/")
    response = RedirectResponse(target, status_code=303)
    if code in i18n.LANGUAGES:
        response.set_cookie("lang", code, max_age=31_536_000, samesite="lax")
    return response


@app.get("/health")
async def health():
    run = db.last_run()
    return JSONResponse({
        "ok": True,
        "repos_tracked": len(db.repos()),
        "last_run": run["started_at"] if run else None,
        "last_run_ok": bool(run["ok"]) if run and run["finished_at"] else None,
        "running": collector.running,
        "pending": collector.pending,
    })


# Whether a tile going up is good news. Open issues, open pull requests and a
# longer CI run are the ones where more is worse.
DELTA_TILES = {
    "stars": True, "forks": True, "watchers": True, "downloads": True,
    "installs": True, "commits": True, "contributors": True, "releases": True,
    "ci_runs": True, "ci_rate": True,
    "issues": False, "prs": False, "ci_seconds": False,
}
ISSUES_EVERY = "issues_minutes"
# how often open issues and pull requests are fetched; the last one is the
# daily full run, which fetches them anyway
ISSUES_CHOICES = (15, 30, 60, 120, 360, 720, 1440)
STICKY = "delta_sticky"
SHOW = "delta_show"
MODE = "delta_mode"
HIDDEN = "hidden_topics"
# what "since" can be measured against, other than the last visit
PERIODS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
MODES = ("visit", *PERIODS)

# snapshot column behind each tile that can be broken down per repository
CHANGE_COLUMNS = {"stars": "stars", "forks": "forks", "watchers": "watchers",
                  "issues": "open_issues", "prs": "open_prs",
                  "downloads": "downloads", "installs": "ha_installs"}


def _tile_values(rows) -> dict:
    """The overview tiles, from rows of {"repo", "snap"}."""
    have = [r["snap"] for r in rows if r["snap"]]
    total = lambda column: sum((s[column] or 0) for s in have)
    return {
        "stars": total("stars"), "forks": total("forks"),
        "watchers": total("watchers"), "issues": total("open_issues"),
        "prs": total("open_prs"), "downloads": total("downloads"),
        "installs": _install_total(rows),
    }


def _repo_values(snap) -> dict:
    return {
        "stars": snap["stars"], "forks": snap["forks"], "watchers": snap["watchers"],
        "issues": snap["open_issues"], "prs": snap["open_prs"],
        "downloads": snap["downloads"], "commits": snap["commits"],
        "contributors": snap["contributors"], "releases": snap["releases"],
        "ci_runs": snap["ci_runs"], "ci_rate": snap["ci_rate"],
        "ci_seconds": snap["ci_seconds"], "installs": snap["ha_installs"],
    }


def _overview_at(repos, moment: str):
    """The overview tiles as they stood at a moment, and the moment actually
    used: a repository with no history that far back falls back to its first
    snapshot, and the comparison can only start there."""
    old = db.snapshots_at(moment)
    rows = [{"repo": r, "snap": old.get(r["full_name"])} for r in repos]
    used = max([moment] + [s["taken_at"] for s in old.values()
                           if s["taken_at"] > moment], default=moment)
    return _tile_values(rows), used


def _repo_at(full_name: str, moment: str):
    old = db.snapshot_at(full_name, moment)
    if not old:
        return None, moment
    return _repo_values(old), max(moment, old["taken_at"])


def _deltas(scope: str, values: dict, lang: str, commit: bool = True,
            past=None) -> dict[str, dict]:
    """What changed on these tiles, against whatever the settings say.

    Against a fixed period the answer comes straight from the stored history
    through `past`, which has no side effects. Against the last visit every
    tile carries its own mark, because the numbers behind them move at very
    different speeds. With the sticky setting on, a mark only moves when the
    number underneath it really changed, so a reload does not wipe the
    reading; with it off, the mark follows every visit.

    A detail page passes commit=False: it reads the same marks the overview
    uses, but must not move them, or the overview would lose its reading.

    Each result also carries "ref", the moment it is measured against, for the
    breakdowns underneath.
    """
    if db.setting(SHOW, "1") != "1":
        return {}

    mode = db.setting(MODE, "visit")
    if mode in PERIODS and past:
        moment = (datetime.now(timezone.utc) - timedelta(hours=PERIODS[mode])
                  ).isoformat(timespec="seconds")
        old, ref = past(moment)
        if old is None:
            return {}
        return {metric: {**_delta(metric, float(value or 0) - float(old.get(metric) or 0),
                                  ref, lang), "ref": ref}
                for metric, value in values.items() if metric in old}

    sticky = db.setting(STICKY, "1") == "1"
    marks = db.baselines(scope)
    shown: dict[str, dict] = {}
    move: dict[str, tuple[float, float]] = {}

    for metric, value in values.items():
        current = float(value or 0)
        mark = marks.get(metric)
        if mark is None:
            # nothing to compare against yet, so this visit only sets the mark
            move[metric] = (current, current)
            continue

        if sticky and current == mark["last_value"]:
            base, when = mark["base_value"], mark["changed_at"]
            ref = mark["base_at"] or mark["changed_at"]
        elif sticky:
            base, when, ref = mark["last_value"], None, mark["changed_at"]
            move[metric] = (mark["last_value"], current)
        else:
            base, when, ref = mark["last_value"], mark["changed_at"], mark["changed_at"]
            move[metric] = (current, current)
        shown[metric] = {**_delta(metric, current - base, when, lang), "ref": ref}

    if move and commit:
        db.write_baselines(scope, move)
    return shown


def _repo_changes(deltas: dict, snapshots: dict, lang: str, metrics) -> dict:
    """Per repository: how much each number moved over the same span as the
    tile above it. Only what really moved is listed."""
    found: dict[str, dict[str, dict]] = {}
    for metric in metrics:
        ref = (deltas.get(metric) or {}).get("ref")
        if not ref:
            continue
        column = CHANGE_COLUMNS[metric]
        old = db.snapshots_at(ref)
        for name, snap in snapshots.items():
            before = old.get(name)
            if not snap or not before:
                continue
            amount = (snap[column] or 0) - (before[column] or 0)
            if amount:
                found.setdefault(name, {})[metric] = _delta(metric, amount, None, lang)
    return found


def _asset_changes(assets, deltas: dict, lang: str) -> dict | None:
    """Per release file: how many downloads came in over the same span as the
    downloads tile. None when changes are switched off; a file with no value
    recorded back then maps to None, which the table shows as a dash."""
    if db.setting(SHOW, "1") != "1":
        return None
    ref = (deltas.get("downloads") or {}).get("ref")
    if not ref or not assets:
        return {}
    old = db.assets_at(ref)
    found: dict[tuple, dict | None] = {}
    for a in assets:
        key = (a["full_name"], a["tag"], a["asset"])
        if key in old:
            found[key] = _delta("downloads", a["downloads"] - old[key], None, lang)
        elif a["published"] and a["published"] > ref:
            # uploaded after the moment in question: all of it is new
            found[key] = _delta("downloads", a["downloads"], None, lang)
        else:
            found[key] = None
    return found


def _delta(metric: str, amount: float, when: str | None, lang: str) -> dict:
    """Dress one difference up for the tile: text, colour, and since when."""
    t = i18n.translator(lang)
    if amount == 0:
        size, mood = i18n.number(0, lang), "flat"
    else:
        if metric == "ci_seconds":
            size = i18n.duration(abs(amount), lang)
        elif metric == "ci_rate":
            size = f"{i18n.number(abs(amount), lang)} %"
        else:
            size = i18n.number(abs(amount), lang)
        rising = amount > 0
        mood = "good" if rising == DELTA_TILES.get(metric, True) else "bad"
    sign = "+" if amount > 0 else ("\u2212" if amount < 0 else "\u00b1")
    # a change noticed on this very request has no earlier moment to name
    return {"text": sign + size, "mood": mood, "value": amount,
            "since": i18n.since(when, lang) if when else t("since.now")}


def _failed_run():
    """The last finished run, if it failed — for the banner at the top."""
    run = db.last_finished_run()
    return run if run and not run["ok"] else None


def _failed_mqtt():
    status = publisher.status()
    return status if status and not status["ok"] else None


def _install_total(rows) -> int:
    """Installations, counted once per integration.

    Home Assistant reports per domain, not per repository, and a domain is
    shared by everyone shipping that integration. What lands in the snapshot
    is therefore already narrowed to the versions released here; this only
    makes sure a domain shipped from two repositories is not counted twice.
    """
    seen: dict[str, int] = {}
    for row in rows:
        snap, repo = row["snap"], row["repo"]
        if not snap or not snap["ha_installs"]:
            continue
        domain = repo["ha_domain"] or repo["full_name"]
        seen[domain] = max(seen.get(domain, 0), snap["ha_installs"])
    return sum(seen.values())


def _carried_total(repos, metric: str, days: int) -> list[dict]:
    """Sum a cumulative per-repository metric, holding the last known value.

    Star counts only have a row on days where something changed, so a plain
    SUM over the rows would drop repositories on their quiet days.
    """
    from datetime import date, timedelta

    window = [(date.today() - timedelta(days=offset)).isoformat()
              for offset in range(days - 1, -1, -1)]
    totals = {day: 0 for day in window}
    for repo in repos:
        rows = {r["day"]: int(r["value"] or 0)
                for r in db.series(repo["full_name"], metric, days=36500)}
        if not rows:
            continue
        running = 0
        for day in sorted(rows):
            if day <= window[0]:
                running = rows[day]
        for day in window:
            if day in rows:
                running = rows[day]
            totals[day] += running
    return [{"day": day, "value": value} for day, value in totals.items()]


def _sum(rows) -> int:
    return sum(int(r["value"] or 0) for r in rows)

