"""A small session login.

Deliberately simple: one account, the password comes from the environment,
and the session is a signed cookie. That is enough for a service on your own
network, and it avoids a user database for a single-person dashboard.

The signing key is kept in the database, so sessions survive a restart. Leave
AUTH_PASSWORD empty and the login is switched off entirely.
"""
import hashlib
import hmac
import os
import secrets
import time

COOKIE = "session"
MAX_AGE = 60 * 60 * 24 * 30          # a month


class Auth:
    def __init__(self, db, user: str, password: str):
        self.user = user or "admin"
        self._password = password or ""
        self._key = self._load_key(db)
        self._failures: dict[str, list[float]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._password)

    # ---- passwords -------------------------------------------------------

    def check(self, user: str, password: str, client: str = "") -> bool:
        """Compare in constant time, and slow down repeated failures."""
        if self._throttled(client):
            return False
        ok = (hmac.compare_digest(user or "", self.user)
              and hmac.compare_digest(password or "", self._password))
        if not ok:
            self._failures.setdefault(client, []).append(time.time())
        else:
            self._failures.pop(client, None)
        return ok

    def _throttled(self, client: str) -> bool:
        recent = [t for t in self._failures.get(client, []) if time.time() - t < 300]
        self._failures[client] = recent
        return len(recent) >= 8

    # ---- sessions --------------------------------------------------------

    def issue(self) -> str:
        expires = int(time.time()) + MAX_AGE
        return f"{expires}.{self._sign(expires)}"

    def valid(self, cookie: str | None) -> bool:
        if not self.enabled:
            return True
        if not cookie or "." not in cookie:
            return False
        raw, _, signature = cookie.partition(".")
        if not raw.isdigit() or int(raw) < time.time():
            return False
        return hmac.compare_digest(signature, self._sign(int(raw)))

    def _sign(self, expires: int) -> str:
        message = f"{expires}:{self.user}".encode()
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    @staticmethod
    def _load_key(db) -> bytes:
        """Read the signing key, creating it once on first start."""
        with db.connect() as con:
            con.execute("CREATE TABLE IF NOT EXISTS secret (name TEXT PRIMARY KEY, value TEXT)")
            row = con.execute("SELECT value FROM secret WHERE name = 'session_key'").fetchone()
            if row:
                return bytes.fromhex(row["value"])
            key = secrets.token_bytes(32)
            con.execute("INSERT INTO secret (name, value) VALUES ('session_key', ?)",
                        (key.hex(),))
            return key


def from_env(db) -> Auth:
    return Auth(db, os.getenv("AUTH_USER", "admin"), os.getenv("AUTH_PASSWORD", ""))
