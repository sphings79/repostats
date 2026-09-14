"""Storage for the collected numbers.

Everything lands in one SQLite file. Daily values are keyed by (repo, metric,
day) so a collection run can be repeated without creating duplicates — which
matters because the traffic endpoints always return the last fourteen days at
once, and re-writing them is how gaps heal after downtime.
"""
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS repo (
    full_name     TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT,
    private       INTEGER NOT NULL DEFAULT 0,
    fork          INTEGER NOT NULL DEFAULT 0,
    archived      INTEGER NOT NULL DEFAULT 0,
    language      TEXT,
    license       TEXT,
    topics        TEXT,
    homepage      TEXT,
    created_at    TEXT,
    pushed_at     TEXT,
    tracked       INTEGER NOT NULL DEFAULT 0,
    ha_domain     TEXT,
    last_seen     TEXT
);

CREATE TABLE IF NOT EXISTS snapshot (
    full_name     TEXT NOT NULL,
    taken_at      TEXT NOT NULL,
    stars         INTEGER,
    forks         INTEGER,
    watchers      INTEGER,
    open_issues   INTEGER,
    open_prs      INTEGER,
    closed_issues INTEGER,
    merged_prs    INTEGER,
    size_kb       INTEGER,
    contributors  INTEGER,
    commits       INTEGER,
    releases      INTEGER,
    downloads     INTEGER,
    ha_installs   INTEGER,
    ci_runs       INTEGER,
    ci_success    INTEGER,
    ci_rate       INTEGER,
    ci_seconds    INTEGER,
    ci_last       TEXT,
    PRIMARY KEY (full_name, taken_at)
);

CREATE TABLE IF NOT EXISTS daily (
    full_name  TEXT NOT NULL,
    day        TEXT NOT NULL,
    metric     TEXT NOT NULL,
    value      INTEGER NOT NULL,
    PRIMARY KEY (full_name, day, metric)
);

CREATE TABLE IF NOT EXISTS referrer (
    full_name  TEXT NOT NULL,
    day        TEXT NOT NULL,
    source     TEXT NOT NULL,
    views      INTEGER NOT NULL,
    uniques    INTEGER NOT NULL,
    PRIMARY KEY (full_name, day, source)
);

CREATE TABLE IF NOT EXISTS popular_path (
    full_name  TEXT NOT NULL,
    day        TEXT NOT NULL,
    path       TEXT NOT NULL,
    title      TEXT,
    views      INTEGER NOT NULL,
    uniques    INTEGER NOT NULL,
    PRIMARY KEY (full_name, day, path)
);

CREATE TABLE IF NOT EXISTS release_asset (
    full_name  TEXT NOT NULL,
    tag        TEXT NOT NULL,
    asset      TEXT NOT NULL,
    downloads  INTEGER NOT NULL,
    published  TEXT,
    PRIMARY KEY (full_name, tag, asset)
);

CREATE TABLE IF NOT EXISTS issue (
    full_name  TEXT NOT NULL,
    number     INTEGER NOT NULL,
    title      TEXT NOT NULL,
    url        TEXT NOT NULL,
    author     TEXT,
    labels     TEXT,
    comments   INTEGER,
    created_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (full_name, number)
);

CREATE TABLE IF NOT EXISTS run (
    started_at  TEXT PRIMARY KEY,
    finished_at TEXT,
    kind        TEXT,
    repos       INTEGER,
    ok          INTEGER,
    note        TEXT
);

CREATE INDEX IF NOT EXISTS daily_lookup ON daily (full_name, metric, day);
CREATE INDEX IF NOT EXISTS snapshot_lookup ON snapshot (full_name, taken_at);
"""

_local = threading.local()


class Database:
    """A thin wrapper; one connection per thread, WAL so reads never block."""

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Add columns that newer versions introduced.

        The file outlives the code, so a column added later has to reach an
        existing database as well.
        """
        wanted = {
            "snapshot": {
                "ci_runs": "INTEGER", "ci_success": "INTEGER", "ci_rate": "INTEGER",
                "ci_seconds": "INTEGER", "ci_last": "TEXT",
            },
        }
        with self.connect() as con:
            for table, columns in wanted.items():
                have = {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns.items():
                    if name not in have:
                        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    def _conn(self) -> sqlite3.Connection:
        con = getattr(_local, "con", None)
        if con is None:
            con = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            _local.con = con
        return con

    @contextmanager
    def connect(self):
        con = self._conn()
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise

    # ---- writes ----------------------------------------------------------

    def upsert_repo(self, repo: dict) -> None:
        with self.connect() as con:
            con.execute(
                """
                INSERT INTO repo (full_name, name, description, private, fork,
                                  archived, language, license, topics, homepage,
                                  created_at, pushed_at, last_seen)
                VALUES (:full_name, :name, :description, :private, :fork,
                        :archived, :language, :license, :topics, :homepage,
                        :created_at, :pushed_at, :last_seen)
                ON CONFLICT(full_name) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    private=excluded.private,
                    fork=excluded.fork,
                    archived=excluded.archived,
                    language=excluded.language,
                    license=excluded.license,
                    topics=excluded.topics,
                    homepage=excluded.homepage,
                    pushed_at=excluded.pushed_at,
                    last_seen=excluded.last_seen
                """,
                {**repo, "last_seen": _now()},
            )

    def set_tracked(self, full_names: list[str]) -> None:
        with self.connect() as con:
            con.execute("UPDATE repo SET tracked = 0")
            for name in full_names:
                con.execute("UPDATE repo SET tracked = 1 WHERE full_name = ?", (name,))

    def set_tracked_one(self, full_name: str, tracked: bool) -> None:
        """Follow or stop following one repository, leaving the rest alone."""
        with self.connect() as con:
            con.execute("UPDATE repo SET tracked = ? WHERE full_name = ?",
                        (1 if tracked else 0, full_name))

    def set_ha_domain(self, full_name: str, domain: str | None) -> None:
        with self.connect() as con:
            con.execute("UPDATE repo SET ha_domain = ? WHERE full_name = ?",
                        (domain or None, full_name))

    def write_snapshot(self, full_name: str, values: dict) -> None:
        cols = ["stars", "forks", "watchers", "open_issues", "open_prs",
                "closed_issues", "merged_prs", "size_kb", "contributors",
                "commits", "releases", "downloads", "ha_installs",
                "ci_runs", "ci_success", "ci_rate", "ci_seconds", "ci_last"]
        row = {c: values.get(c) for c in cols}
        row["full_name"] = full_name
        row["taken_at"] = _now()
        with self.connect() as con:
            con.execute(
                f"""INSERT OR REPLACE INTO snapshot
                    (full_name, taken_at, {', '.join(cols)})
                    VALUES (:full_name, :taken_at, {', '.join(':' + c for c in cols)})""",
                row,
            )

    def write_daily(self, full_name: str, metric: str, points: list[tuple[str, int]]) -> None:
        with self.connect() as con:
            con.executemany(
                """INSERT INTO daily (full_name, day, metric, value)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(full_name, day, metric) DO UPDATE SET
                       value = MAX(excluded.value, daily.value)""",
                [(full_name, day, metric, value) for day, value in points],
            )

    def write_referrers(self, full_name: str, rows: list[dict]) -> None:
        today = date.today().isoformat()
        with self.connect() as con:
            con.executemany(
                """INSERT OR REPLACE INTO referrer (full_name, day, source, views, uniques)
                   VALUES (?, ?, ?, ?, ?)""",
                [(full_name, today, r["referrer"], r["count"], r["uniques"]) for r in rows],
            )

    def write_paths(self, full_name: str, rows: list[dict]) -> None:
        today = date.today().isoformat()
        with self.connect() as con:
            con.executemany(
                """INSERT OR REPLACE INTO popular_path
                   (full_name, day, path, title, views, uniques)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [(full_name, today, r["path"], r.get("title"), r["count"], r["uniques"])
                 for r in rows],
            )

    def write_assets(self, full_name: str, rows: list[tuple]) -> None:
        with self.connect() as con:
            con.executemany(
                """INSERT OR REPLACE INTO release_asset
                   (full_name, tag, asset, downloads, published)
                   VALUES (?, ?, ?, ?, ?)""",
                [(full_name, *r) for r in rows],
            )

    def write_issues(self, full_name: str, rows: list[dict]) -> None:
        """Replace what is stored for a repository; closed ones simply vanish."""
        with self.connect() as con:
            con.execute("DELETE FROM issue WHERE full_name = ?", (full_name,))
            con.executemany(
                """INSERT OR REPLACE INTO issue
                   (full_name, number, title, url, author, labels, comments,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(full_name, r["number"], r["title"], r["html_url"],
                  (r.get("user") or {}).get("login"),
                  ",".join(l["name"] for l in r.get("labels", [])),
                  r.get("comments", 0), r.get("created_at"), r.get("updated_at"))
                 for r in rows],
            )

    def issues(self, full_name: str | None = None) -> list[sqlite3.Row]:
        sql = """SELECT i.* FROM issue i
                 JOIN repo r ON r.full_name = i.full_name AND r.tracked = 1"""
        params: tuple = ()
        if full_name:
            sql += " WHERE i.full_name = ?"
            params = (full_name,)
        sql += " ORDER BY i.updated_at DESC"
        with self.connect() as con:
            return con.execute(sql, params).fetchall()

    def start_run(self, kind: str) -> str:
        started = _now()
        with self.connect() as con:
            con.execute("INSERT INTO run (started_at, kind) VALUES (?, ?)", (started, kind))
        return started

    def finish_run(self, started: str, repos: int, ok: bool, note: str = "") -> None:
        with self.connect() as con:
            con.execute(
                "UPDATE run SET finished_at = ?, repos = ?, ok = ?, note = ? WHERE started_at = ?",
                (_now(), repos, 1 if ok else 0, note[:500], started),
            )

    # ---- reads -----------------------------------------------------------

    def repos(self, tracked_only: bool = True) -> list[sqlite3.Row]:
        sql = "SELECT * FROM repo"
        if tracked_only:
            sql += " WHERE tracked = 1"
        sql += " ORDER BY full_name COLLATE NOCASE"
        with self.connect() as con:
            return con.execute(sql).fetchall()

    def repo(self, full_name: str) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute("SELECT * FROM repo WHERE full_name = ?", (full_name,)).fetchone()

    def latest_snapshot(self, full_name: str) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM snapshot WHERE full_name = ? ORDER BY taken_at DESC LIMIT 1",
                (full_name,)).fetchone()

    def latest_snapshots(self) -> dict[str, sqlite3.Row]:
        with self.connect() as con:
            rows = con.execute("""
                SELECT s.* FROM snapshot s
                JOIN (SELECT full_name, MAX(taken_at) AS t FROM snapshot GROUP BY full_name) m
                  ON s.full_name = m.full_name AND s.taken_at = m.t
            """).fetchall()
        return {r["full_name"]: r for r in rows}

    def series(self, full_name: str, metric: str, days: int = 90) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT day, value FROM daily
                   WHERE full_name = ? AND metric = ?
                     AND day >= date('now', ?)
                   ORDER BY day""",
                (full_name, metric, f"-{days} day")).fetchall()

    def totals_series(self, metric: str, days: int = 90) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT day, SUM(value) AS value FROM daily
                   WHERE metric = ? AND day >= date('now', ?)
                     AND full_name IN (SELECT full_name FROM repo WHERE tracked = 1)
                   GROUP BY day ORDER BY day""",
                (metric, f"-{days} day")).fetchall()

    def snapshot_series(self, column: str, days: int = 90) -> list[sqlite3.Row]:
        """One point per day for a counter, taken from the last run of that day."""
        if not column.isidentifier():
            raise ValueError(column)
        with self.connect() as con:
            return con.execute(
                f"""SELECT substr(taken_at, 1, 10) AS day, SUM(value) AS value FROM (
                        SELECT full_name, taken_at, {column} AS value,
                               ROW_NUMBER() OVER (
                                   PARTITION BY full_name, substr(taken_at, 1, 10)
                                   ORDER BY taken_at DESC) AS rn
                        FROM snapshot
                        WHERE full_name IN (SELECT full_name FROM repo WHERE tracked = 1)
                          AND taken_at >= datetime('now', ?)
                    ) WHERE rn = 1
                    GROUP BY day ORDER BY day""",
                (f"-{days} day",)).fetchall()

    def repo_snapshot_series(self, full_name: str, column: str, days: int = 90):
        if not column.isidentifier():
            raise ValueError(column)
        with self.connect() as con:
            return con.execute(
                f"""SELECT substr(taken_at, 1, 10) AS day, {column} AS value FROM (
                        SELECT taken_at, {column},
                               ROW_NUMBER() OVER (
                                   PARTITION BY substr(taken_at, 1, 10)
                                   ORDER BY taken_at DESC) AS rn
                        FROM snapshot
                        WHERE full_name = ? AND taken_at >= datetime('now', ?)
                    ) WHERE rn = 1 ORDER BY day""",
                (full_name, f"-{days} day")).fetchall()

    def referrers(self, full_name: str, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT source, views, uniques FROM referrer
                   WHERE full_name = ? AND day = (SELECT MAX(day) FROM referrer WHERE full_name = ?)
                   ORDER BY views DESC LIMIT ?""",
                (full_name, full_name, limit)).fetchall()

    def paths(self, full_name: str, limit: int = 10) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT path, title, views, uniques FROM popular_path
                   WHERE full_name = ? AND day = (SELECT MAX(day) FROM popular_path WHERE full_name = ?)
                   ORDER BY views DESC LIMIT ?""",
                (full_name, full_name, limit)).fetchall()

    def assets(self, full_name: str | None = None) -> list[sqlite3.Row]:
        """Release files of one repository, or of all followed ones."""
        if full_name:
            sql = """SELECT full_name, tag, asset, downloads, published
                     FROM release_asset WHERE full_name = ?
                     ORDER BY published DESC, asset"""
            params: tuple = (full_name,)
        else:
            sql = """SELECT a.full_name, a.tag, a.asset, a.downloads, a.published
                     FROM release_asset a
                     JOIN repo r ON r.full_name = a.full_name AND r.tracked = 1
                     WHERE a.downloads > 0
                     ORDER BY a.downloads DESC LIMIT 60"""
            params = ()
        with self.connect() as con:
            return con.execute(sql, params).fetchall()

    def top_referrers(self, limit: int = 12) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                """SELECT source, SUM(views) AS views, SUM(uniques) AS uniques
                   FROM referrer r
                   WHERE day = (SELECT MAX(day) FROM referrer)
                     AND full_name IN (SELECT full_name FROM repo WHERE tracked = 1)
                   GROUP BY source ORDER BY views DESC LIMIT ?""",
                (limit,)).fetchall()

    def last_run(self) -> sqlite3.Row | None:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM run ORDER BY started_at DESC LIMIT 1").fetchone()

    def runs(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as con:
            return con.execute(
                "SELECT * FROM run ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
