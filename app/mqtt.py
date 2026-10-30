"""Publishes the collected numbers to an MQTT broker for Home Assistant.

Every followed repository becomes one device, and one more device carries the
totals. The entities are announced through MQTT discovery, so nothing has to
be configured on the Home Assistant side. Everything is published retained: a
restart of Home Assistant finds the last values waiting.

A broker that cannot be reached never fails a collection run. The outcome of
the last attempt is kept in the settings table and shown as a banner.
"""
import asyncio
import json
import logging
import re
import ssl
from datetime import datetime, timezone

import aiomqtt

from .db import Database

_LOGGER = logging.getLogger(__name__)

DEFAULTS = {
    "enabled": "0",
    "host": "192.168.181.223",
    "port": "1883",
    "user": "",
    "password": "",
    "base": "repostats",
    "prefix": "homeassistant",
    "tls": "0",
    "tls_verify": "1",
}
TIMEOUT = 10

# key, name, unit, icon, state class — in the order they appear in Home Assistant
REPO_SENSORS = [
    ("stars", "Stars", None, "mdi:star", "measurement"),
    ("forks", "Forks", None, "mdi:source-fork", "measurement"),
    ("watchers", "Watchers", None, "mdi:eye", "measurement"),
    ("open_issues", "Open issues", None, "mdi:alert-circle-outline", "measurement"),
    ("closed_issues", "Closed issues", None, "mdi:check-circle-outline", "total_increasing"),
    ("open_prs", "Open pull requests", None, "mdi:source-pull", "measurement"),
    ("merged_prs", "Merged pull requests", None, "mdi:source-merge", "total_increasing"),
    ("contributors", "Contributors", None, "mdi:account-group", "measurement"),
    ("commits", "Commits", None, "mdi:source-commit", "total_increasing"),
    ("releases", "Releases", None, "mdi:tag-multiple", "measurement"),
    ("downloads", "Downloads", None, "mdi:download", "total_increasing"),
    ("ha_installs", "Home Assistant installations", None, "mdi:home-assistant", "measurement"),
    ("size_kb", "Size", "kB", "mdi:database", "measurement"),
    ("ci_runs", "CI runs", None, "mdi:cog-play", "measurement"),
    ("ci_rate", "CI success rate", "%", "mdi:check-decagram", "measurement"),
    ("ci_seconds", "CI duration", "s", "mdi:timer-outline", "measurement"),
    ("ci_last", "CI last result", None, "mdi:check-network", None),
    ("views", "Views (14 days)", None, "mdi:eye-outline", "measurement"),
    ("views_unique", "Unique visitors (14 days)", None, "mdi:account-eye", "measurement"),
    ("clones", "Clones (14 days)", None, "mdi:content-copy", "measurement"),
    ("clones_unique", "Unique cloners (14 days)", None, "mdi:account-arrow-down", "measurement"),
]

TOTAL_SENSORS = [
    ("repos", "Repositories", None, "mdi:github", "measurement"),
] + [s for s in REPO_SENSORS
     if s[0] not in ("ci_runs", "ci_rate", "ci_seconds", "ci_last")] + [
    ("last_run", "Last run", None, "mdi:clock-check-outline", None),
    ("last_run_status", "Last run result", None, "mdi:check-circle", None),
]

# Counters that are summed for the totals device.
SUMMED = [s[0] for s in REPO_SENSORS if not s[0].startswith("ci_")]


def read_config(db: Database) -> dict:
    return {key: db.setting(f"mqtt_{key}", default) for key, default in DEFAULTS.items()}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _tls_context(config: dict) -> ssl.SSLContext | None:
    if config["tls"] != "1":
        return None
    context = ssl.create_default_context()
    if config["tls_verify"] != "1":
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _client(config: dict) -> aiomqtt.Client:
    return aiomqtt.Client(
        hostname=config["host"],
        port=int(config["port"] or 1883),
        username=config["user"] or None,
        password=config["password"] or None,
        tls_context=_tls_context(config),
        timeout=TIMEOUT,
    )


def _sensor_config(config: dict, device_id: str, device: dict, state_topic: str,
                   sensor: tuple) -> tuple[str, dict]:
    key, name, unit, icon, state_class = sensor
    topic = f"{config['prefix']}/sensor/{device_id}/{key}/config"
    payload = {
        "name": name,
        "unique_id": f"{device_id}_{key}",
        "state_topic": state_topic,
        "value_template": f"{{{{ value_json.{key} }}}}",
        "icon": icon,
        "device": device,
    }
    if unit:
        payload["unit_of_measurement"] = unit
    if state_class:
        payload["state_class"] = state_class
    if key == "last_run":
        payload["device_class"] = "timestamp"
        del payload["icon"]
    return topic, payload


class Publisher:
    def __init__(self, db: Database, install_total):
        self.db = db
        self._install_total = install_total
        self._lock = asyncio.Lock()

    # ---- what to publish -------------------------------------------------

    def _states(self) -> tuple[dict[str, dict], dict]:
        """State of every followed repository, and the totals."""
        snapshots = self.db.latest_snapshots()
        repos = self.db.repos()
        per_repo: dict[str, dict] = {}
        rows = []
        for repo in repos:
            name = repo["full_name"]
            snap = snapshots.get(name)
            rows.append({"repo": repo, "snap": snap})
            if snap is None:
                continue
            state = {key: snap[key] for key, *_ in REPO_SENSORS
                     if key in snap.keys() and snap[key] is not None}
            if not repo["ha_domain"]:
                state.pop("ha_installs", None)
            for metric in ("views", "clones", "views_unique", "clones_unique"):
                state[metric] = sum(int(r["value"] or 0)
                                    for r in self.db.series(name, metric, 14))
            per_repo[name] = state

        total = {"repos": len(repos)}
        for key in SUMMED:
            total[key] = sum((state.get(key) or 0) for state in per_repo.values())
        total["ha_installs"] = self._install_total(rows)

        run = self.db.last_finished_run()
        if run:
            total["last_run"] = run["started_at"]
            total["last_run_status"] = "ok" if run["ok"] else "failed"
        return per_repo, total

    # ---- publishing ------------------------------------------------------

    async def publish(self) -> None:
        """Publish now. Never raises; the outcome goes to the settings table."""
        config = read_config(self.db)
        if config["enabled"] != "1":
            return
        async with self._lock:
            try:
                await asyncio.wait_for(self._publish(config), timeout=60)
                self._record(True, "")
            except Exception as err:                       # noqa: BLE001
                _LOGGER.warning("MQTT publish failed: %s", _describe(err))
                self._record(False, _describe(err))

    async def _publish(self, config: dict) -> None:
        per_repo, total = self._states()
        base, previous = config["base"].strip("/"), self._published()
        current = {name: _slug(name) for name in per_repo}

        async with _client(config) as client:
            async def send(topic: str, payload) -> None:
                body = payload if isinstance(payload, str) else json.dumps(payload)
                await client.publish(topic, body, qos=1, retain=True)

            for name, state in per_repo.items():
                slug = current[name]
                device_id = f"repostats_{slug}"
                device = {"identifiers": [device_id], "name": name.split("/")[-1],
                          "manufacturer": "Repo Stats", "model": "GitHub repository",
                          "configuration_url": f"https://github.com/{name}"}
                state_topic = f"{base}/{slug}/state"
                for sensor in REPO_SENSORS:
                    if sensor[0] in state:
                        topic, payload = _sensor_config(
                            config, device_id, device, state_topic, sensor)
                        await send(topic, payload)
                await send(state_topic, state)

            device = {"identifiers": ["repostats_total"], "name": "Repo Stats",
                      "manufacturer": "Repo Stats", "model": "Totals"}
            state_topic = f"{base}/total/state"
            for sensor in TOTAL_SENSORS:
                if sensor[0] in total:
                    topic, payload = _sensor_config(
                        config, "repostats_total", device, state_topic, sensor)
                    await send(topic, payload)
            await send(state_topic, total)

            # A repository that is no longer followed leaves Home Assistant:
            # an empty retained config removes the entity, and with it the device.
            for name in previous:
                if name in current:
                    continue
                slug = _slug(name)
                for sensor in REPO_SENSORS:
                    await send(f"{config['prefix']}/sensor/repostats_{slug}/"
                               f"{sensor[0]}/config", "")
                await send(f"{base}/{slug}/state", "")

        self.db.set_setting("mqtt_published", json.dumps(sorted(current)))

    def _published(self) -> list[str]:
        try:
            return json.loads(self.db.setting("mqtt_published", "[]"))
        except ValueError:
            return []

    def _record(self, ok: bool, error: str) -> None:
        self.db.set_setting("mqtt_ok", "1" if ok else "0")
        self.db.set_setting("mqtt_error", error[:300])
        self.db.set_setting("mqtt_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))

    # ---- connection test -------------------------------------------------

    async def test(self, config: dict) -> str:
        """Connect and disconnect again. Returns an empty string on success."""
        try:
            async with _client(config):
                pass
        except Exception as err:                           # noqa: BLE001
            return _describe(err)
        return ""

    def status(self) -> dict | None:
        """The outcome of the last attempt, or None when MQTT is off or untried."""
        if self.db.setting("mqtt_enabled", "0") != "1":
            return None
        ok = self.db.setting("mqtt_ok", "")
        if not ok:
            return None
        return {"ok": ok == "1", "error": self.db.setting("mqtt_error", ""),
                "at": self.db.setting("mqtt_at", "")}


def _describe(err: BaseException) -> str:
    text = str(err).strip()
    return f"{type(err).__name__}: {text}" if text else type(err).__name__
