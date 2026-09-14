"""Collects the numbers and writes them away.

Two kinds of run:

* "full"  — once a day. Traffic, referrers, popular paths, release assets,
            issue splits, contributors, commits. The traffic endpoints return
            the last fourteen days in one go, so this also repairs gaps left
            by downtime shorter than two weeks.
* "quick" — hourly. The cheap counters: stars, forks, watchers, downloads.
"""
import asyncio
import logging
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from . import ha_analytics
from .db import Database
from .github import GitHub, RateLimited

_LOGGER = logging.getLogger(__name__)


class Collector:
    def __init__(self, db: Database, token: str, login: str, star_token: str = ""):
        self.db = db
        self.token = token
        self.login = login
        self.star_token = star_token
        self._lock = asyncio.Lock()
        self.running: str | None = None

    async def discover(self) -> int:
        """Refresh the repository list without touching any statistics."""
        github = GitHub(self.token, self.login, star_token=self.star_token)
        try:
            repos = await github.repos()
            for repo in repos:
                self.db.upsert_repo(_repo_row(repo))
            return len(repos)
        finally:
            await github.aclose()

    async def run(self, kind: str = "full") -> dict:
        if self._lock.locked():
            return {"skipped": "a collection is already running"}

        async with self._lock:
            self.running = kind
            started = self.db.start_run(kind)
            github = GitHub(self.token, self.login, star_token=self.star_token)
            done, note, ok = 0, "", True
            try:
                for repo in await github.repos():
                    self.db.upsert_repo(_repo_row(repo))

                tracked = self.db.repos(tracked_only=True)
                installs = await ha_analytics.fetch() if kind == "full" else {}

                for row in tracked:
                    try:
                        await self._one(github, row, kind, installs)
                        done += 1
                    except RateLimited as err:
                        ok, note = False, str(err)
                        _LOGGER.warning("Stopping early: %s", err)
                        break
                    except Exception as err:               # noqa: BLE001
                        note = f"{row['full_name']}: {err}"
                        _LOGGER.exception("Failed on %s", row["full_name"])
            except Exception as err:                       # noqa: BLE001
                ok, note = False, str(err)
                _LOGGER.exception("Collection failed")
            finally:
                await github.aclose()
                self.db.finish_run(started, done, ok, note)
                self.running = None

            return {"kind": kind, "repos": done, "ok": ok, "note": note}

    async def _one(self, github: GitHub, row, kind: str, installs: dict) -> None:
        full_name = row["full_name"]
        repo = await github.repo(full_name)
        if not repo:
            return

        values = {
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "watchers": repo.get("subscribers_count", 0),
            "size_kb": repo.get("size", 0),
        }

        releases = await github.releases(full_name)
        tags = {_normalise(r.get("tag_name", "")) for r in releases}
        assets = []
        downloads = 0
        for release in releases:
            for asset in release.get("assets", []):
                downloads += asset.get("download_count", 0)
                assets.append((release.get("tag_name", "?"), asset["name"],
                               asset.get("download_count", 0),
                               release.get("published_at")))
        values["releases"] = len(releases)
        values["downloads"] = downloads
        if assets:
            self.db.write_assets(full_name, assets)

        if kind == "full":
            values.update(await github.issue_counts(full_name))
            values["contributors"] = await github.contributors(full_name)
            values["commits"] = await github.commit_count(full_name)

            for metric, points in (("views", await github.views(full_name)),
                                   ("clones", await github.clones(full_name))):
                if points:
                    self.db.write_daily(full_name, metric,
                                        [(day, count) for day, count, _u in points])
                    self.db.write_daily(full_name, f"{metric}_unique",
                                        [(day, uniques) for day, _c, uniques in points])

            referrers = await github.referrers(full_name)
            if referrers:
                self.db.write_referrers(full_name, referrers)
            paths = await github.paths(full_name)
            if paths:
                self.db.write_paths(full_name, paths)

            await self._star_history(github, full_name, repo)
            values.update(await self._ci(github, full_name))

            # Only ask when the count says there is something to list.
            if values.get("open_issues"):
                self.db.write_issues(full_name, await github.open_issues(full_name))
            else:
                self.db.write_issues(full_name, [])

            domain = row["ha_domain"]
            if domain is None:
                domain = await ha_analytics.domain_for(github, full_name)
                self.db.set_ha_domain(full_name, domain)
            if domain and domain in installs:
                self._installs(full_name, installs[domain], tags, values)
        else:
            previous = self.db.latest_snapshot(full_name)
            if previous:
                for key in ("open_issues", "open_prs", "closed_issues", "merged_prs",
                            "contributors", "commits", "ha_installs",
                            "ha_installs_total",
                            "ci_runs", "ci_success", "ci_rate", "ci_seconds", "ci_last"):
                    values[key] = previous[key]

        self.db.write_snapshot(full_name, values)

    def _installs(self, full_name: str, entry: dict, tags: set, values: dict) -> None:
        """Split the reported installations into ours and everybody else's.

        An integration domain belongs to whoever ships it, not to a
        repository. A project continuing somebody else's work — or sharing a
        domain with a predecessor — sees their users in the total. The
        versions tell them apart: only the ones released here are ours.
        """
        versions = entry.get("versions", {})
        total = entry.get("total", 0)

        rows = [(version, count, _normalise(version) in tags)
                for version, count in versions.items()]
        mine = sum(count for _v, count, is_mine in rows if is_mine)

        # No release of ours shows up: either the versions cannot be matched
        # or nobody runs this build yet. Reporting the whole domain would be
        # claiming other people's users, so it is kept separate.
        values["ha_installs"] = mine
        values["ha_installs_total"] = total

        if rows:
            self.db.write_ha_versions(full_name, rows)
        if mine:
            self.db.write_daily(full_name, "ha_installs",
                                [(date.today().isoformat(), mine)])

    async def _ci(self, github: GitHub, full_name: str) -> dict:
        """Success rate and duration of the workflow runs.

        Only finished runs count: a run still in progress has no conclusion
        and would otherwise drag the rate down for no reason.
        """
        runs = await github.workflow_runs(full_name)
        finished = [r for r in runs if r.get("conclusion")]
        if not finished:
            return {}

        good = [r for r in finished if r["conclusion"] == "success"]
        seconds = []
        for run in finished:
            started, ended = run.get("run_started_at"), run.get("updated_at")
            if not started or not ended:
                continue
            try:
                delta = (datetime.fromisoformat(ended.replace("Z", "+00:00"))
                         - datetime.fromisoformat(started.replace("Z", "+00:00")))
            except ValueError:
                continue
            if 0 < delta.total_seconds() < 86400:
                seconds.append(delta.total_seconds())

        per_day = Counter(r["created_at"][:10] for r in finished)
        failures = Counter(r["created_at"][:10] for r in finished
                           if r["conclusion"] != "success")
        self.db.write_daily(full_name, "ci_runs", sorted(per_day.items()))
        if failures:
            self.db.write_daily(full_name, "ci_failures", sorted(failures.items()))

        return {
            "ci_runs": len(finished),
            "ci_success": len(good),
            "ci_rate": round(len(good) / len(finished) * 100),
            "ci_seconds": round(sum(seconds) / len(seconds)) if seconds else None,
            "ci_last": finished[0]["conclusion"],
        }

    async def _star_history(self, github: GitHub, full_name: str, repo: dict) -> None:
        """Rebuild the star curve from the dates GitHub keeps per stargazer."""
        if repo.get("stargazers_count", 0) == 0:
            return
        existing = self.db.series(full_name, "stars_total", days=36500)
        if existing and len(existing) > 1:
            latest = existing[-1]["value"]
            if latest == repo["stargazers_count"]:
                return

        dates = await github.stargazer_dates(full_name)
        if not dates:
            return
        per_day = Counter(dates)
        running, points = 0, []
        start = min(per_day)
        today = date.today()
        day = date.fromisoformat(start)
        while day <= today:
            running += per_day.get(day.isoformat(), 0)
            points.append((day.isoformat(), running))
            day += timedelta(days=1)
        self.db.write_daily(full_name, "stars_total", points)


def _normalise(version: str) -> str:
    """Compare a release tag with a version string from the analytics.

    Tags carry a leading v often enough that ignoring it is worth more than
    being strict: v2.1.1 and 2.1.1 are the same release.
    """
    return (version or "").strip().lstrip("vV")


def _repo_row(repo: dict) -> dict:
    return {
        "full_name": repo["full_name"],
        "name": repo["name"],
        "description": repo.get("description"),
        "private": 1 if repo.get("private") else 0,
        "fork": 1 if repo.get("fork") else 0,
        "archived": 1 if repo.get("archived") else 0,
        "language": repo.get("language"),
        "license": (repo.get("license") or {}).get("spdx_id"),
        "topics": ",".join(repo.get("topics") or []),
        "homepage": repo.get("homepage"),
        "created_at": repo.get("created_at"),
        "pushed_at": repo.get("pushed_at"),
    }
