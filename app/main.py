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

from . import auth as auth_module, charts, i18n
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
auth = auth_module.from_env(db)


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
        "installs": sum((r["snap"]["ha_installs"] or 0) for r in rows if r["snap"]),
        "views": sum(r["views"] for r in rows),
        "clones": sum(r["clones"] for r in rows),
        "views_unique": sum(r["views_unique"] for r in rows),
        "clones_unique": sum(r["clones_unique"] for r in rows),
    }

    traffic = charts.area_chart([
        {"label": t("chart.views"), "rows": db.totals_series("views", days),
         "colour": "var(--accent)"},
        {"label": t("chart.clones"), "rows": db.totals_series("clones", days),
         "colour": "var(--accent-2)"},
    ], days=days, lang=lang)
    growth = charts.area_chart([
        {"label": t("chart.stars"), "rows": _carried_total(repos, "stars_total", days),
         "colour": "var(--gold)", "carry": True},
        {"label": t("chart.downloads"), "rows": db.snapshot_series("downloads", days),
         "colour": "var(--violet)", "carry": True},
    ], days=days, lang=lang)

    return _render(request, "index.html", {
        "rows": rows, "totals": totals, "traffic": traffic, "growth": growth,
        "referrers": charts.bars(db.top_referrers(), "source", "views", lang=lang),
        "days": days, "last_run": db.last_run(), "running": collector.running,
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
    stars = charts.area_chart([
        {"label": t("chart.stars"), "rows": db.series(full_name, "stars_total", days),
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

    installs = None
    if repo["ha_domain"]:
        installs = charts.area_chart([
            {"label": t("chart.installs"), "rows": db.series(full_name, "ha_installs", days),
             "colour": "var(--accent-2)", "carry": True},
        ], days=days, lang=lang)

    return _render(request, "repo.html", {
        "repo": repo, "snap": snap, "days": days,
        "traffic": traffic, "clones": clones, "stars": stars, "installs": installs,
        "ci": ci,
        "referrers": charts.bars(db.referrers(full_name), "source", "views", lang=lang),
        "paths": charts.bars(db.paths(full_name), "path", "views", lang=lang),
        "assets": db.assets(full_name),
        "views14": _sum(db.series(full_name, "views", 14)),
        "clones14": _sum(db.series(full_name, "clones", 14)),
        "uniques14": _sum(db.series(full_name, "views_unique", 14)),
        "clone_uniques14": _sum(db.series(full_name, "clones_unique", 14)),
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


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    return _render(request, "settings.html", {
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

