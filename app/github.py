"""Everything this dashboard reads out of the GitHub API.

Only the REST API is used, with a personal access token. Traffic and clone
figures need one — they are private to the repository owner — which is the
reason the collector runs server-side instead of in the browser.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

_LOGGER = logging.getLogger(__name__)

API = "https://api.github.com"
PER_PAGE = 100


class RateLimited(Exception):
    """Raised when the API asks us to come back later."""


class GitHub:
    def __init__(self, token: str, login: str, timeout: float = 30.0,
                 star_token: str = ""):
        self.login = login
        self._star_token = star_token
        self._public: httpx.AsyncClient | None = None
        self._client = httpx.AsyncClient(
            base_url=API,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "repostats",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()
        if self._public is not None:
            await self._public.aclose()

    def _star_client(self) -> httpx.AsyncClient | None:
        """A client for the stargazers endpoint, if a token for it exists.

        GitHub refuses fine-grained tokens there, over REST and GraphQL alike,
        and the endpoint is not open to anonymous callers either. A classic
        token with the public_repo scope is what it accepts; it is kept apart
        from the main token so the one that reads private repositories does
        not have to grow write access to public ones.
        """
        if not self._star_token:
            return None
        if self._public is None:
            self._public = httpx.AsyncClient(
                base_url=API,
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self._star_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "repostats",
                },
            )
        return self._public

    async def _get(self, path: str, **params) -> Any:
        """One request, with a polite retry when the rate limit is hit."""
        for attempt in range(3):
            response = await self._client.get(path, params=params or None)

            if response.status_code == 403 and "rate limit" not in response.text.lower():
                # A token without this particular permission — the rest of the
                # run is still worth finishing.
                _LOGGER.debug("No access to %s", path)
                return None

            if response.status_code == 403 and "rate limit" in response.text.lower():
                reset = int(response.headers.get("x-ratelimit-reset", "0"))
                wait = max(reset - int(datetime.now(timezone.utc).timestamp()), 1)
                if wait > 900 or attempt == 2:
                    raise RateLimited(f"rate limited for another {wait}s")
                _LOGGER.warning("Rate limited, waiting %ss", wait)
                await asyncio.sleep(wait)
                continue

            # A repository can simply have no traffic data yet, and forks
            # report no contributor list; neither is worth failing a run over.
            if response.status_code in (204, 404, 409):
                return None

            response.raise_for_status()
            return response.json()
        return None

    async def _paged(self, path: str, **params) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            batch = await self._get(path, per_page=PER_PAGE, page=page, **params)
            if not batch:
                break
            out.extend(batch)
            if len(batch) < PER_PAGE:
                break
            page += 1
            if page > 50:            # a safety net, not a real limit
                break
        return out

    # ---- repositories ----------------------------------------------------

    async def repos(self) -> list[dict]:
        """Every repository the token can see for this account."""
        raw = await self._paged("/user/repos", affiliation="owner", sort="full_name")
        return [r for r in raw if r["owner"]["login"].lower() == self.login.lower()]

    async def repo(self, full_name: str) -> dict | None:
        return await self._get(f"/repos/{full_name}")

    # ---- counters --------------------------------------------------------

    async def issue_counts(self, full_name: str) -> dict:
        """Issues and pull requests, split apart.

        GitHub counts pull requests as issues in `open_issues_count`, so the
        number on the repository object is not what a person means by "open
        issues". The search API gives the honest split.
        """
        out = {}
        for key, query in (
            ("open_issues", f"repo:{full_name} is:issue is:open"),
            ("closed_issues", f"repo:{full_name} is:issue is:closed"),
            ("open_prs", f"repo:{full_name} is:pr is:open"),
            ("merged_prs", f"repo:{full_name} is:pr is:merged"),
        ):
            result = await self._get("/search/issues", q=query, per_page=1)
            out[key] = (result or {}).get("total_count", 0)
            await asyncio.sleep(2.2)   # the search API allows 30 requests a minute
        return out

    async def contributors(self, full_name: str) -> int:
        rows = await self._get(f"/repos/{full_name}/contributors", per_page=1, anon="true")
        if rows is None:
            return 0
        return len(await self._paged(f"/repos/{full_name}/contributors", anon="true"))

    async def commit_count(self, full_name: str) -> int:
        """Total commits on the default branch, read from the Link header."""
        response = await self._client.get(
            f"/repos/{full_name}/commits", params={"per_page": 1})
        if response.status_code != 200:
            return 0
        link = response.headers.get("link", "")
        for part in link.split(","):
            if 'rel="last"' in part:
                page = part.split("page=")[-1].split(">")[0].split("&")[0]
                if page.isdigit():
                    return int(page)
        return len(response.json() or [])

    # ---- traffic (owner only) -------------------------------------------

    async def views(self, full_name: str) -> list[tuple[str, int, int]]:
        data = await self._get(f"/repos/{full_name}/traffic/views")
        return _traffic_points(data)

    async def clones(self, full_name: str) -> list[tuple[str, int, int]]:
        data = await self._get(f"/repos/{full_name}/traffic/clones")
        return _traffic_points(data)

    async def referrers(self, full_name: str) -> list[dict]:
        return await self._get(f"/repos/{full_name}/traffic/popular/referrers") or []

    async def paths(self, full_name: str) -> list[dict]:
        return await self._get(f"/repos/{full_name}/traffic/popular/paths") or []

    # ---- releases and history -------------------------------------------

    async def releases(self, full_name: str) -> list[dict]:
        return await self._paged(f"/repos/{full_name}/releases")

    async def stargazer_dates(self, full_name: str, cap: int = 3000) -> list[str]:
        """When each star was given.

        This is the one history GitHub hands out retroactively, so a fresh
        install can draw a star curve that reaches back years instead of
        starting flat at today.
        """
        out: list[str] = []
        page = 1
        client = self._client
        headers = {"Accept": "application/vnd.github.star+json"}

        while len(out) < cap:
            response = await client.get(
                f"/repos/{full_name}/stargazers",
                params={"per_page": PER_PAGE, "page": page},
                headers=headers,
            )
            if response.status_code in (401, 403) and client is self._client:
                fallback = self._star_client()
                if fallback is None:
                    _LOGGER.info(
                        "No star history: this token may not read stargazers. "
                        "Set GITHUB_TOKEN_STARS to a classic token with the "
                        "public_repo scope to get the curve back to the first "
                        "star.")
                    break
                client = fallback
                response = await client.get(
                    f"/repos/{full_name}/stargazers",
                    params={"per_page": PER_PAGE, "page": page},
                    headers=headers,
                )
            if response.status_code != 200:
                if page == 1:
                    _LOGGER.info(
                        "No star history for %s: the stargazers endpoint "
                        "answered %s. A classic token with the public_repo "
                        "scope in GITHUB_TOKEN_STARS is what it accepts.",
                        full_name, response.status_code)
                break
            batch = response.json() or []
            out.extend(row["starred_at"][:10] for row in batch if "starred_at" in row)
            if len(batch) < PER_PAGE:
                break
            page += 1
        return out

    async def fork_dates(self, full_name: str, cap: int = 1000) -> list[str]:
        rows = await self._paged(f"/repos/{full_name}/forks", sort="oldest")
        return [r["created_at"][:10] for r in rows[:cap]]

    async def open_issues(self, full_name: str) -> list[dict]:
        """Open issues without the pull requests GitHub mixes in."""
        rows = await self._paged(f"/repos/{full_name}/issues", state="open")
        return [r for r in rows if "pull_request" not in r]

    async def workflow_runs(self, full_name: str, limit: int = 100) -> list[dict]:
        """The most recent workflow runs, for the CI figures."""
        data = await self._get(f"/repos/{full_name}/actions/runs",
                               per_page=min(limit, PER_PAGE))
        return (data or {}).get("workflow_runs", [])

    async def rate_limit(self) -> dict:
        data = await self._get("/rate_limit")
        return (data or {}).get("resources", {})


def _traffic_points(data: dict | None) -> list[tuple[str, int, int]]:
    if not data:
        return []
    return [(row["timestamp"][:10], row["count"], row["uniques"])
            for row in data.get("views", data.get("clones", []))]
