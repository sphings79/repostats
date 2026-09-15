"""A small session login.

Deliberately simple: one account, kept in the database, and the session is a
signed cookie. That is enough for a service on your own network, and it avoids
a user database for a single-person dashboard.

The password is stored as an scrypt hash, never in clear. The signing key sits
in the database as well, so sessions survive a restart; rotating it is how
"sign out everywhere" is done. Until an account exists, the application sends
every visitor to the setup page — there is no way to run this without a login.
"""
import hashlib
import hmac
import secrets
import time

COOKIE = "session"
MAX_AGE = 60 * 60 * 24 * 30          # a month
MIN_PASSWORD = 12

# n, r, p — about 16 MB of memory per check, which is the point of scrypt.
# They travel with the hash, so raising them later leaves old hashes readable.
SCRYPT = (2 ** 14, 8, 1)


class Auth:
    def __init__(self, db):
        self.db = db
        self._key = self._load_key(db)
        self._failures: dict[str, list[float]] = {}

    @property
    def configured(self) -> bool:
        """False until someone has been through the setup page."""
        return self.db.account() is not None

    @property
    def user(self) -> str:
        row = self.db.account()
        return row["name"] if row else ""

    # ---- passwords -------------------------------------------------------

    def check(self, user: str, password: str, client: str = "") -> bool:
        """The login form: name and password together."""
        row = self.db.account()
        if row is None or self._throttled(client):
            return False
        ok = hmac.compare_digest(user or "", row["name"]) and _verify(password, row["secret"])
        self._note(client, ok)
        return ok

    def verify(self, password: str, client: str = "") -> bool:
        """Confirm the password of the account that is already signed in."""
        row = self.db.account()
        if row is None or self._throttled(client):
            return False
        ok = _verify(password, row["secret"])
        self._note(client, ok)
        return ok

    def create(self, name: str, password: str) -> None:
        self.db.write_account(name.strip(), _hash(password))

    def set_name(self, name: str) -> None:
        row = self.db.account()
        self.db.write_account(name.strip(), row["secret"])

    def set_password(self, password: str) -> None:
        row = self.db.account()
        self.db.write_account(row["name"], _hash(password))

    def _note(self, client: str, ok: bool) -> None:
        if ok:
            self._failures.pop(client, None)
        else:
            self._failures.setdefault(client, []).append(time.time())

    def _throttled(self, client: str) -> bool:
        """Slow down repeated failures from one caller."""
        recent = [t for t in self._failures.get(client, []) if time.time() - t < 300]
        self._failures[client] = recent
        return len(recent) >= 8

    # ---- sessions --------------------------------------------------------

    def issue(self) -> str:
        expires = int(time.time()) + MAX_AGE
        return f"{expires}.{self._sign(expires, self.user)}"

    def valid(self, cookie: str | None) -> bool:
        row = self.db.account()
        if row is None or not cookie or "." not in cookie:
            return False
        raw, _, signature = cookie.partition(".")
        if not raw.isdigit() or int(raw) < time.time():
            return False
        return hmac.compare_digest(signature, self._sign(int(raw), row["name"]))

    def rotate_key(self) -> None:
        """A new signing key, which ends every session but the one reissued."""
        key = secrets.token_bytes(32)
        with self.db.connect() as con:
            con.execute("UPDATE secret SET value = ? WHERE name = 'session_key'",
                        (key.hex(),))
        self._key = key

    def _sign(self, expires: int, name: str) -> str:
        # The name is part of the signature, so renaming the account ends the
        # sessions that were signed for the old one.
        message = f"{expires}:{name}".encode()
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


def problem(name: str, password: str, repeat: str) -> str | None:
    """What is wrong with these credentials, as a translation key."""
    if not name.strip():
        return "account.error.name"
    if len(password) < MIN_PASSWORD:
        return "account.error.short"
    if password != repeat:
        return "account.error.match"
    return None


def _hash(password: str) -> str:
    n, r, p = SCRYPT
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return f"scrypt${n}${r}${p}${salt.hex()}${key.hex()}"


def _verify(password: str, stored: str) -> bool:
    try:
        kind, n, r, p, salt, key = stored.split("$")
        if kind != "scrypt":
            return False
        want = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt),
                              n=int(n), r=int(r), p=int(p), dklen=len(key) // 2)
    except ValueError:
        return False
    return hmac.compare_digest(want.hex(), key)
