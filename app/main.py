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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth as auth_module, charts, i18n
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
auth = auth_module.from_env(db)


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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(_scheduler())
    yield
    task.cancel()


app = FastAPI(title="Repo Stats", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

OPEN_PATHS = ("/login", "/health", "/static", "/lang")


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Everything but the login page needs a valid session."""
    path = request.url.path
    if auth.enabled and not path.startswith(OPEN_PATHS):
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
        "auth_enabled": auth.enabled,
        "asset_version": ASSETS,
        "source_url": SOURCE_URL,
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
        "stars": sum((r["snap"]["stars"] or 0) for r in rows if r["snap"]),
        "forks": sum((r["snap"]["forks"] or 0) for r in rows if r["snap"]),
        "watchers": sum((r["snap"]["watchers"] or 0) for r in rows if r["snap"]),
        "issues": sum((r["snap"]["open_issues"] or 0) for r in rows if r["snap"]),
        "downloads": sum((r["snap"]["downloads"] or 0) for r in rows if r["snap"]),
        "installs": _install_total(rows),
        "views": sum(r["views"] for r in rows),
        "clones": sum(r["clones"] for r in rows),
        "views_unique": sum(r["views_unique"] for r in rows),
        "clones_unique": sum(r["clones_unique"] for r in rows),
    }

    # Only once there is something to compare; before the first run every
    # tile would set its mark to zero and report a jump afterwards.
    deltas = _deltas("overview", {
        "stars": totals["stars"], "forks": totals["forks"],
        "watchers": totals["watchers"], "downloads": totals["downloads"],
        "installs": totals["installs"], "issues": totals["issues"],
    }, lang) if snapshots else {}

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
        "deltas": deltas,
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

    deltas = _deltas(full_name, {
        "stars": snap["stars"], "forks": snap["forks"], "watchers": snap["watchers"],
        "issues": snap["open_issues"], "prs": snap["open_prs"],
        "downloads": snap["downloads"], "commits": snap["commits"],
        "contributors": snap["contributors"], "releases": snap["releases"],
        "ci_runs": snap["ci_runs"], "ci_rate": snap["ci_rate"],
        "ci_seconds": snap["ci_seconds"], "installs": snap["ha_installs"],
    }, lang) if snap else {}

    return _render(request, "repo.html", {
        "repo": repo, "snap": snap, "days": days, "deltas": deltas,
        "traffic": traffic, "clones": clones, "stars": stars, "installs": installs,
        "ci": ci, "versions": versions, "hidden_versions": hidden_versions,
        "referrers": charts.bars(db.referrers(full_name), "source", "views", lang=lang),
        "paths": charts.bars(db.paths(full_name), "path", "views", lang=lang),
        "assets": db.assets(full_name),
        "views14": _sum(db.series(full_name, "views", 14)),
        "clones14": _sum(db.series(full_name, "clones", 14)),
        "uniques14": _sum(db.series(full_name, "views_unique", 14)),
        "clone_uniques14": _sum(db.series(full_name, "clones_unique", 14)),
    })


# Which repository column or daily metric sits behind each tile.
BREAKDOWN = {
    "stars":     {"column": "stars",     "title": "kpi.stars"},
    "forks":     {"column": "forks",     "title": "kpi.forks"},
    "watchers":  {"column": "watchers",  "title": "kpi.watchers"},
    "downloads": {"column": "downloads", "title": "kpi.downloads"},
    "installs":  {"column": "ha_installs", "title": "kpi.installs.long"},
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

    return _render(request, "top.html", {
        "metric": metric, "rows": rows, "total": total,
        "second_total": second_total, "days": days,
        "title": t(spec["title"]), "note": note,
        "assets": db.assets(None) if metric == "downloads" else None,
        "last_run": db.last_run(),
    })


@app.get("/issues", response_class=HTMLResponse)
async def issues(request: Request, repo: str | None = None):
    """Every open issue across the followed repositories, with links."""
    rows = db.issues(repo)
    per_repo: dict[str, list] = {}
    for row in rows:
        per_repo.setdefault(row["full_name"], []).append(row)

    return _render(request, "issues.html", {
        "groups": sorted(per_repo.items(), key=lambda kv: (-len(kv[1]), kv[0])),
        "total": len(rows),
        "single": repo,
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


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return _render(request, "settings.html", {
        "repos": db.repos(tracked_only=False),
        "runs": db.runs(),
        "running": collector.running,
        "pending": collector.pending,
        "login": LOGIN,
        "has_token": bool(TOKEN),
        "sticky": db.setting(STICKY, "1") == "1",
    })


@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    db.set_tracked(form.getlist("tracked"))
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/display")
async def save_display(request: Request):
    """Its own form: the one below it carries the tracked repositories, and
    posting that without them would clear every tick."""
    form = await request.form()
    db.set_setting(STICKY, "1" if form.get("sticky") else "0")
    return RedirectResponse("/settings", status_code=303)


@app.post("/discover")
async def discover():
    found = await collector.discover()
    _LOGGER.info("Repository list refreshed: %s entries", found)
    return RedirectResponse("/settings", status_code=303)


@app.post("/collect")
async def collect(kind: str = Form("full")):
    asyncio.create_task(collector.run("quick" if kind == "quick" else "full"))
    return RedirectResponse("/settings", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/"):
    if not auth.enabled or auth.valid(request.cookies.get(auth_module.COOKIE)):
        return RedirectResponse("/", status_code=303)
    return _render(request, "login.html", {"next": next, "failed": False})


@app.post("/login")
async def login(request: Request, user: str = Form(""), password: str = Form(""),
                next: str = Form("/")):
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
STICKY = "delta_sticky"


def _deltas(scope: str, values: dict, lang: str) -> dict[str, dict]:
    """What changed on these tiles since the page was last opened.

    Every tile carries its own mark, because the numbers behind them move at
    very different speeds. With the sticky setting on, a mark only moves when
    the number underneath it really changed, so a reload does not wipe the
    reading; with it off, the mark follows every visit.
    """
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
        elif sticky:
            base, when = mark["last_value"], None
            move[metric] = (mark["last_value"], current)
        else:
            base, when = mark["last_value"], mark["changed_at"]
            move[metric] = (current, current)
        shown[metric] = _delta(metric, current - base, when, lang)

    if move:
        db.write_baselines(scope, move)
    return shown


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
    return {"text": sign + size, "mood": mood,
            "since": i18n.since(when, lang) if when else t("since.now")}


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

