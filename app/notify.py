"""Notifications: tells the owner when something needs a look.

Channels: Telegram (bot API), Pushover, Home Assistant `notify` (REST API with
a long-lived token) and a webhook (POST to a URL of your choice, JSON or plain
text, optional Authorization header). Only the request to the configured
address leaves the container.

What is reported, checked after every collection run:

* a new open issue, and a new open pull request (bots can be left out; a
  repository carrying a hidden topic stays silent). More than a handful of
  new ones in one run become a single message.
* a collection run that failed, and a failed MQTT publish.
* the all-clear once those work again.

One message per incident. What has been seen is kept in the database, so a
restart does not repeat anything, and a repository that has only just been
followed is taken in silently. A message that cannot be delivered waits in a
queue (retried every minute, at most 24 hours, at most 50 messages), and at
most 30 messages per hour leave the container.

The tokens and the webhook address are kept with the other settings, never
sent back to the page, and never written to the log.
"""
import json
import logging
import os
import re
import time
from collections.abc import Callable

import httpx

from .db import Database

_LOGGER = logging.getLogger(__name__)

QUEUE_MAX = 50
QUEUE_AGE = 24 * 3600
PER_HOUR = 30
GROUP_OVER = 5          # more new items than this in one run become one message
GROUP_LINES = 10

DEFAULTS = {
    "enabled": False,
    "lang": "en",
    "telegram": {"enabled": False, "chat_id": ""},
    "ha": {"enabled": False, "url": "", "service": "notify", "insecure": False},
    "pushover": {"enabled": False, "priority": 0},
    "webhook": {"enabled": False, "format": "json", "insecure": False},
    "rules": {
        "issues": True, "pulls": True, "bots": False,
        "run_failed": True, "mqtt_failed": True, "recovery": True,
    },
}

MSG = {
    "en": {
        "issue": lambda r, n, title, who, url:
            f"🐞 New issue in {r}: #{n} {title}" + (f" (by @{who})" if who else "") + f"\n{url}",
        "pull": lambda r, n, title, who, url:
            f"🔀 New pull request in {r}: #{n} {title}" + (f" (by @{who})" if who else "") + f"\n{url}",
        "issues_many": lambda n, repos: f"🐞 {n} new issues in {repos} {'repository' if repos == 1 else 'repositories'}:",
        "pulls_many": lambda n, repos: f"🔀 {n} new pull requests in {repos} {'repository' if repos == 1 else 'repositories'}:",
        "and_more": lambda n: f"… and {n} more",
        "run_failed": lambda note: "⚠ The last collection failed" + (f": {note}" if note else "."),
        "run_ok": lambda: "✅ Collections are working again.",
        "mqtt_failed": lambda error: "⚠ Publishing to MQTT failed" + (f": {error}" if error else "."),
        "mqtt_ok": lambda: "✅ Publishing to MQTT works again.",
        "test": lambda: "✅ Test message from Repo Stats.",
    },
    "de": {
        "issue": lambda r, n, title, who, url:
            f"🐞 Neues Issue in {r}: #{n} {title}" + (f" (von @{who})" if who else "") + f"\n{url}",
        "pull": lambda r, n, title, who, url:
            f"🔀 Neuer Pull Request in {r}: #{n} {title}" + (f" (von @{who})" if who else "") + f"\n{url}",
        "issues_many": lambda n, repos: f"🐞 {n} neue Issues in {repos} {'Repository' if repos == 1 else 'Repositories'}:",
        "pulls_many": lambda n, repos: f"🔀 {n} neue Pull Requests in {repos} {'Repository' if repos == 1 else 'Repositories'}:",
        "and_more": lambda n: f"… und {n} weitere",
        "run_failed": lambda note: "⚠ Der letzte Abruf ist fehlgeschlagen" + (f": {note}" if note else "."),
        "run_ok": lambda: "✅ Die Abrufe laufen wieder.",
        "mqtt_failed": lambda error: "⚠ Das Senden an MQTT ist fehlgeschlagen" + (f": {error}" if error else "."),
        "mqtt_ok": lambda: "✅ Das Senden an MQTT funktioniert wieder.",
        "test": lambda: "✅ Testnachricht von Repo Stats.",
    },
}

TITLE = "Repo Stats"
URL_RE = re.compile(r"^https?://[^\s/]+(:\d+)?(/[^\s]*)?$")
TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")
CHAT_RE = re.compile(r"^(-?\d{1,20}|@[A-Za-z0-9_]{5,32})$")
SERVICE_RE = re.compile(r"^[a-z0-9_]{1,80}$")
CHANNELS = ("telegram", "ha", "pushover", "webhook")
SECRET_KEYS = ("telegram_token", "ha_token", "pushover_token", "pushover_user",
               "webhook_url", "webhook_auth")
# which secrets belong to which channel, for "remove"
SECRETS_OF = {
    "telegram": ("telegram_token",), "ha": ("ha_token",),
    "pushover": ("pushover_token", "pushover_user"),
    "webhook": ("webhook_url", "webhook_auth"),
}


def normalise(raw: dict | None) -> dict:
    """A stored or submitted config, merged into the defaults. Anything that is
    not a known setting is dropped."""
    c = raw or {}
    on = lambda value, default: default if value is None else bool(value)
    section = lambda name: c.get(name) if isinstance(c.get(name), dict) else {}
    tg, ha, po, wh, rules = (section(n) for n in ("telegram", "ha", "pushover", "webhook", "rules"))
    d = DEFAULTS["rules"]
    priority = po.get("priority", 0)
    return {
        "enabled": c.get("enabled") is True,
        "lang": "de" if c.get("lang") == "de" else "en",
        "telegram": {"enabled": bool(tg.get("enabled")),
                     "chat_id": str(tg.get("chat_id") or "").strip()[:64]},
        "ha": {"enabled": bool(ha.get("enabled")), "insecure": bool(ha.get("insecure")),
               "url": str(ha.get("url") or "").strip().rstrip("/")[:200],
               "service": re.sub(r"^notify\.", "", str(ha.get("service") or "notify").strip(),
                                 flags=re.I)[:80]},
        "pushover": {"enabled": bool(po.get("enabled")),
                     "priority": priority if priority in (-1, 0, 1) else 0},
        "webhook": {"enabled": bool(wh.get("enabled")),
                    "format": "text" if wh.get("format") == "text" else "json",
                    "insecure": bool(wh.get("insecure"))},
        "rules": {key: on(rules.get(key), d[key]) for key in d},
    }


def validate(c: dict) -> str | None:
    """The reason a config cannot be accepted, or None."""
    if c["telegram"]["chat_id"] and not CHAT_RE.match(c["telegram"]["chat_id"]):
        return "badChatId"
    if c["ha"]["url"] and not URL_RE.match(c["ha"]["url"]):
        return "badUrl"
    if not SERVICE_RE.match(c["ha"]["service"]):
        return "badService"
    return None


async def _request(method: str, url: str, *, headers=None, json_body=None, content=None,
                   insecure: bool = False) -> dict:
    """One request with a timeout and no redirects. Never raises, and never puts
    the address in an error, because it may carry a secret."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False,
                                     verify=not insecure) as client:
            response = await client.request(method, url, headers=headers,
                                            json=json_body, content=content)
    except httpx.InvalidURL:
        return {"ok": False, "error": "badUrl"}
    except httpx.HTTPError as err:
        return {"ok": False, "error": type(err).__name__}
    return {"ok": 200 <= response.status_code < 300, "status": response.status_code,
            "body": response.text[:2000]}


class Notifier:
    def __init__(self, db: Database, hidden_topics: Callable[[], set[str]], send=None):
        self.db = db
        self.hidden_topics = hidden_topics
        self._send = send or self._deliver_one
        self._state = None

    # ---- stored things ---------------------------------------------------

    def config(self) -> dict:
        try:
            return normalise(json.loads(self.db.setting("notify_config", "{}")))
        except ValueError:
            return normalise({})

    def save_config(self, config: dict) -> None:
        self.db.set_setting("notify_config", json.dumps(config))

    def secrets(self) -> dict:
        try:
            stored = json.loads(self.db.setting("notify_secrets", "{}"))
        except ValueError:
            stored = {}
        return {key: str(stored.get(key) or "") for key in SECRET_KEYS}

    def save_secrets(self, secrets: dict) -> None:
        self.db.set_setting("notify_secrets", json.dumps(
            {key: value for key, value in secrets.items() if value and key in SECRET_KEYS}))

    def flags(self) -> dict:
        """What is set, without saying what it is."""
        s = self.secrets()
        host = ""
        if s["webhook_url"]:
            host = re.sub(r"^https?://", "", s["webhook_url"]).split("/")[0]
        return {"telegram": bool(s["telegram_token"]), "ha": bool(s["ha_token"]),
                "pushover": bool(s["pushover_token"] and s["pushover_user"]),
                "webhook": bool(s["webhook_url"]), "webhook_host": host,
                "webhook_auth": bool(s["webhook_auth"])}

    @property
    def state(self) -> dict:
        if self._state is None:
            try:
                loaded = json.loads(self.db.setting("notify_state", "{}"))
            except ValueError:
                loaded = {}
            self._state = {"active": {}, "queue": [], "sent": [], "last_sent": None,
                           "last_error": None, **loaded}
        return self._state

    def _save(self) -> None:
        self.db.set_setting("notify_state", json.dumps(self.state))

    def status(self) -> dict:
        s = self.state
        return {"queue": len(s["queue"]), "last_sent": s["last_sent"],
                "last_error": s["last_error"], "active": sorted(s["active"])}

    # ---- channels --------------------------------------------------------

    async def _deliver_one(self, channel: str, c: dict, s: dict, text: str, meta: dict) -> dict:
        title = TITLE
        if channel == "telegram":
            if not s["telegram_token"] or not c["telegram"]["chat_id"]:
                return {"ok": False, "error": "notConfigured"}
            base = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
            r = await _request("POST", f"{base}/bot{s['telegram_token']}/sendMessage",
                               json_body={"chat_id": c["telegram"]["chat_id"], "text": text,
                                          "disable_web_page_preview": True})
        elif channel == "pushover":
            if not s["pushover_token"] or not s["pushover_user"]:
                return {"ok": False, "error": "notConfigured"}
            base = os.getenv("PUSHOVER_API_BASE", "https://api.pushover.net")
            r = await _request("POST", f"{base}/1/messages.json", json_body={
                "token": s["pushover_token"], "user": s["pushover_user"], "title": title,
                "message": text, "priority": c["pushover"]["priority"]})
            if r["ok"]:
                try:
                    r["ok"] = json.loads(r["body"]).get("status") == 1
                except ValueError:
                    r["ok"] = False
                if not r["ok"]:
                    r["error"] = "refused"
        elif channel == "ha":
            if not s["ha_token"] or not c["ha"]["url"]:
                return {"ok": False, "error": "notConfigured"}
            r = await _request(
                "POST", f"{c['ha']['url']}/api/services/notify/{c['ha']['service']}",
                headers={"Authorization": f"Bearer {s['ha_token']}"},
                json_body={"message": text, "title": title}, insecure=c["ha"]["insecure"])
            if r.get("status") == 404:
                return {"ok": False,
                        "error": f"http 404: notify.{c['ha']['service']} does not exist in Home Assistant"}
        else:
            if not s["webhook_url"]:
                return {"ok": False, "error": "notConfigured"}
            headers = {"Title": title}
            if s["webhook_auth"]:
                headers["Authorization"] = s["webhook_auth"]
            if c["webhook"]["format"] == "text":
                r = await _request("POST", s["webhook_url"], headers={
                    **headers, "Content-Type": "text/plain; charset=utf-8"},
                    content=text.encode(), insecure=c["webhook"]["insecure"])
            else:
                body = {"title": title, "message": text, "event": meta.get("event", "test"),
                        "repo": meta.get("repo"), "number": meta.get("number"),
                        "url": meta.get("url"),
                        "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                r = await _request("POST", s["webhook_url"], headers=headers, json_body=body,
                                   insecure=c["webhook"]["insecure"])
        if r["ok"]:
            return r
        return {**r, "ok": False, "error": r.get("error") or f"http {r.get('status')}"}

    async def _deliver(self, text: str, meta: dict, only=None) -> list[str]:
        """Try every enabled channel; return the ones that did not take it."""
        c, s = self.config(), self.secrets()
        failed = []
        for channel in CHANNELS:
            if not c[channel]["enabled"] or (only and channel not in only):
                continue
            r = await self._send(channel, c, s, text, meta)
            if r["ok"]:
                self.state["last_sent"] = time.time()
                self.state["last_error"] = None
            else:
                failed.append(channel)
                self.state["last_error"] = {"ts": time.time(), "channel": channel,
                                            "error": str(r.get("error"))}
                _LOGGER.warning("Notification via %s failed: %s", channel, r.get("error"))
        return failed

    async def notify(self, text: str, meta: dict | None = None) -> None:
        """Send now, or queue it when it cannot be delivered. Over the hourly
        limit it is dropped."""
        c = self.config()
        if not c["enabled"] or not any(c[ch]["enabled"] for ch in CHANNELS):
            return
        meta = meta or {}
        now = time.time()
        state = self.state
        state["sent"] = [t for t in state["sent"] if now - t < 3600]
        if len(state["sent"]) >= PER_HOUR:
            _LOGGER.warning("Notification dropped: hourly limit reached")
            return
        state["sent"].append(now)
        failed = await self._deliver(text, meta)
        if failed and len(state["queue"]) < QUEUE_MAX:
            state["queue"].append({"ts": now, "text": text, "meta": meta, "channels": failed})
        self._save()

    async def retry(self) -> None:
        """Another go at what could not be delivered."""
        state = self.state
        now = time.time()
        state["queue"] = [q for q in state["queue"] if now - q["ts"] < QUEUE_AGE]
        if not state["queue"]:
            return
        keep = []
        for entry in state["queue"]:
            failed = await self._deliver(entry["text"], entry["meta"], entry["channels"])
            if failed:
                keep.append({**entry, "channels": failed})
        state["queue"] = keep
        self._save()

    async def test(self, channel: str) -> dict:
        c, s = self.config(), self.secrets()
        if channel not in CHANNELS:
            return {"ok": False, "error": "badRequest"}
        c[channel] = {**c[channel], "enabled": True}
        r = await self._send(channel, c, s, MSG[c["lang"]]["test"](), {"event": "test"})
        return {"ok": bool(r["ok"]), "error": None if r["ok"] else str(r.get("error"))}

    # ---- after every run -------------------------------------------------

    async def after_run(self) -> None:
        """Look at what the run left behind. Must not raise."""
        try:
            await self._scan()
            await self._incidents()
        except Exception:                                   # noqa: BLE001
            _LOGGER.exception("Notification check failed")

    async def _scan(self) -> None:
        c = self.config()
        rules = c["rules"]
        t = MSG[c["lang"]]
        db = self.db

        issues, pulls = db.issues(), db.pulls()
        repos = db.repos()
        known = {name for name, _ in db.seen("repo")}
        seen_issues, seen_pulls = db.seen("issue"), db.seen("pull")
        topics = {r["full_name"]: {x for x in (r["topics"] or "").split(",") if x} for r in repos}
        hidden = self.hidden_topics()

        def fresh(rows, seen):
            return [r for r in rows
                    if r["full_name"] in known and (r["full_name"], r["number"]) not in seen
                    and not (topics.get(r["full_name"], set()) & hidden)]

        new_issues = fresh(issues, seen_issues) if rules["issues"] else []
        new_pulls = fresh(pulls, seen_pulls) if rules["pulls"] else []
        if not rules["bots"]:
            new_pulls = [r for r in new_pulls if not r["is_bot"]]

        # taken in before anything is sent: a crash must not repeat them
        db.replace_seen(issues, pulls, [r["full_name"] for r in repos])

        for kind, rows in (("issue", new_issues), ("pull", new_pulls)):
            if not rows:
                continue
            if len(rows) > GROUP_OVER:
                names = {r["full_name"] for r in rows}
                lines = [f"• {r['full_name']} #{r['number']} {r['title']}" for r in rows[:GROUP_LINES]]
                if len(rows) > GROUP_LINES:
                    lines.append(t["and_more"](len(rows) - GROUP_LINES))
                head = t[f"{kind}s_many" if kind == "pull" else "issues_many"](len(rows), len(names))
                await self.notify("\n".join([head, *lines]), {"event": f"{kind}s_new"})
                continue
            for r in rows:
                await self.notify(
                    t[kind](r["full_name"], r["number"], r["title"], r["author"], r["url"]),
                    {"event": f"{kind}_new", "repo": r["full_name"], "number": r["number"],
                     "url": r["url"]})

    async def _incidents(self) -> None:
        c = self.config()
        rules, t = c["rules"], MSG[c["lang"]]
        state = self.state

        run = self.db.last_finished_run()
        mqtt = self._mqtt_status()
        checks = (
            ("run", rules["run_failed"], bool(run and not run["ok"]),
             lambda: t["run_failed"]((run["note"] or "")[:200]), t["run_ok"], "run_failed"),
            ("mqtt", rules["mqtt_failed"], bool(mqtt and not mqtt["ok"]),
             lambda: t["mqtt_failed"]((mqtt["error"] or "")[:200]), t["mqtt_ok"], "mqtt_failed"),
        )
        for key, wanted, failing, opened, closed, event in checks:
            if failing and key not in state["active"]:
                # remembered even when switched off, so switching it on later
                # does not report something that has been going on for days
                state["active"][key] = {"since": time.time(), "told": bool(wanted)}
                if wanted:
                    await self.notify(opened(), {"event": event})
            elif not failing and key in state["active"]:
                told = state["active"].pop(key).get("told")
                if told and rules["recovery"]:
                    await self.notify(closed(), {"event": event.replace("failed", "ok")})
        self._save()

    def _mqtt_status(self) -> dict | None:
        if self.db.setting("mqtt_enabled", "0") != "1":
            return None
        ok = self.db.setting("mqtt_ok", "")
        if not ok:
            return None
        return {"ok": ok == "1", "error": self.db.setting("mqtt_error", "")}
