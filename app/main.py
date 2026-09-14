"""The web application: one overview, one page per repository, one settings page."""
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

from . import charts
from .collector import Collector
from .db import Database

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
_LOGGER = logging.getLogger("repostats")

BASE = Path(__file__).parent
TOKEN = os.getenv("GITHUB_TOKEN", "")
LOGIN = os.getenv("GITHUB_LOGIN", "")
DB_PATH = os.getenv("DB_PATH", "/data/repostats.db")
FULL_HOUR = int(os.getenv("FULL_RUN_HOUR", "4"))
QUICK_MINUTES = int(os.getenv("QUICK_RUN_MINUTES", "60"))

db = Database(DB_PATH)
collector = Collector(db, TOKEN, LOGIN)


async def _scheduler() -> None:
    """Hourly counters, one full run a day, and a full run on an empty database."""
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
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["num"] = lambda v: f"{int(v or 0):,}".replace(",", ".")
templates.env.filters["ago"] = lambda v: _ago(v)


@app.get("/", response_class=HTMLResponse)
async def overview(request: Request, days: int = 30):
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
        "installs": sum((r["snap"]["ha_installs"] or 0) for r in rows if r["snap"]),
        "views": sum(r["views"] for r in rows),
        "clones": sum(r["clones"] for r in rows),
    }

    traffic = charts.area_chart([
        {"label": "Aufrufe", "rows": db.totals_series("views", days), "colour": "var(--accent)"},
        {"label": "Clones", "rows": db.totals_series("clones", days), "colour": "var(--accent-2)"},
    ], days=days)
    growth = charts.area_chart([
        {"label": "Sterne", "rows": _carried_total(repos, "stars_total", days),
         "colour": "var(--gold)", "carry": True},
        {"label": "Downloads", "rows": db.snapshot_series("downloads", days),
         "colour": "var(--violet)", "carry": True},
    ], days=days)

    return templates.TemplateResponse(request, "index.html", {
        "rows": rows, "totals": totals, "traffic": traffic, "growth": growth,
        "referrers": charts.bars(db.top_referrers(), "source", "views"),
        "spark": charts.sparkline, "days": days,
        "last_run": db.last_run(), "running": collector.running,
    })


@app.get("/repo/{owner}/{name}", response_class=HTMLResponse)
async def repo_page(request: Request, owner: str, name: str, days: int = 30):
    full_name = f"{owner}/{name}"
    repo = db.repo(full_name)
    if repo is None:
        return RedirectResponse("/", status_code=303)

    snap = db.latest_snapshot(full_name)
    traffic = charts.area_chart([
        {"label": "Aufrufe", "rows": db.series(full_name, "views", days),
         "colour": "var(--accent)"},
        {"label": "Eindeutige Besucher", "rows": db.series(full_name, "views_unique", days),
         "colour": "var(--accent-2)"},
    ], days=days)
    clones = charts.area_chart([
        {"label": "Clones", "rows": db.series(full_name, "clones", days),
         "colour": "var(--accent-2)"},
        {"label": "Eindeutig", "rows": db.series(full_name, "clones_unique", days),
         "colour": "var(--violet)"},
    ], days=days)
    stars = charts.area_chart([
        {"label": "Sterne", "rows": db.series(full_name, "stars_total", days),
         "colour": "var(--gold)", "carry": True},
    ], days=days)
    installs = None
    if repo["ha_domain"]:
        installs = charts.area_chart([
            {"label": "Installationen", "rows": db.series(full_name, "ha_installs", days),
             "colour": "var(--accent-2)", "carry": True},
        ], days=days)

    return templates.TemplateResponse(request, "repo.html", {
        "repo": repo, "snap": snap, "days": days,
        "traffic": traffic, "clones": clones, "stars": stars, "installs": installs,
        "referrers": charts.bars(db.referrers(full_name), "source", "views"),
        "paths": charts.bars(db.paths(full_name), "path", "views"),
        "assets": db.assets(full_name),
        "views14": _sum(db.series(full_name, "views", 14)),
        "clones14": _sum(db.series(full_name, "clones", 14)),
        "uniques14": _sum(db.series(full_name, "views_unique", 14)),
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return templates.TemplateResponse(request, "settings.html", {
        "repos": db.repos(tracked_only=False),
        "runs": db.runs(),
        "running": collector.running,
        "login": LOGIN,
        "has_token": bool(TOKEN),
    })


@app.post("/settings")
async def save_settings(request: Request):
    form = await request.form()
    db.set_tracked(form.getlist("tracked"))
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


@app.get("/health")
async def health():
    run = db.last_run()
    return JSONResponse({
        "ok": True,
        "repos_tracked": len(db.repos()),
        "last_run": run["started_at"] if run else None,
        "last_run_ok": bool(run["ok"]) if run else None,
        "running": collector.running,
    })


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


def _ago(value: str | None) -> str:
    if not value:
        return "—"
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - moment
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "gerade eben"
    if minutes < 60:
        return f"vor {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"vor {hours} h"
    days = hours // 24
    if days < 30:
        return f"vor {days} d"
    return moment.strftime("%d.%m.%Y")
