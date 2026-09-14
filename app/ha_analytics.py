"""Installation counts from the Home Assistant analytics.

Instances that opted into analytics report which custom integrations they run.
It is the only number here that counts people actually using something, rather
than people looking at it — so for the Home Assistant repositories it is the
figure that matters most.
"""
import logging

import httpx

_LOGGER = logging.getLogger(__name__)

URL = "https://analytics.home-assistant.io/custom_integrations.json"


async def fetch(timeout: float = 30.0) -> dict[str, int]:
    """Map integration domain -> number of reporting installations."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(URL)
            response.raise_for_status()
            data = response.json()
    except Exception as err:                       # noqa: BLE001 - never fail a run
        _LOGGER.warning("Could not read Home Assistant analytics: %s", err)
        return {}

    return {domain: entry.get("total", 0) for domain, entry in data.items()
            if isinstance(entry, dict)}


async def domain_for(github, full_name: str) -> str | None:
    """Find the integration domain a repository ships, if it ships one.

    Custom integrations live in custom_components/<domain>/manifest.json, so
    the domain is the directory name. Reading the tree costs one request and
    saves guessing from the repository name.
    """
    try:
        repo = await github.repo(full_name)
        if not repo:
            return None
        branch = repo.get("default_branch") or "main"
        tree = await github._get(f"/repos/{full_name}/git/trees/{branch}",
                                 recursive="1")
        if not tree:
            return None
        for entry in tree.get("tree", []):
            path = entry.get("path", "")
            if path.startswith("custom_components/") and path.endswith("/manifest.json"):
                return path.split("/")[1]
    except Exception as err:                       # noqa: BLE001
        _LOGGER.debug("No integration domain for %s: %s", full_name, err)
    return None
