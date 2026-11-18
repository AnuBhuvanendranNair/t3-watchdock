"""SQLite storage (stdlib sqlite3): projects, settings, run history, log and app state; replaces config.json + state.json.

One shared connection, serialised by a lock (the app is one process with a few threads). WAL mode, file mode 600.
Existing files are imported once, in the same transaction as the schema version that replaces them, and then renamed
to <name>.imported-<time> (backup): state.json with version 1, config.json with version 2.
"""
import contextlib
import datetime
import json
import os
import sqlite3
import threading

from .core import CONFIG, DATA, STATE

DB_FILE = DATA / "watchdock.db"
LOG_KEEP = 10000          # newest log entries kept (state.json kept 200)

SCHEMA = [
    # version 1
    """
    CREATE TABLE log (id INTEGER PRIMARY KEY AUTOINCREMENT, t TEXT NOT NULL, msg TEXT NOT NULL);
    CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, t TEXT NOT NULL, project TEXT NOT NULL,
        pipeline INTEGER NOT NULL, web_url TEXT, trigger TEXT, ref TEXT);
    CREATE INDEX runs_project ON runs (project, id DESC);
    CREATE TABLE scheduler (task TEXT PRIMARY KEY, last_run TEXT, finished TEXT, ok INTEGER, result TEXT);
    CREATE TABLE typo3_seen (project TEXT PRIMARY KEY, version TEXT NOT NULL);
    CREATE TABLE typo3_announced (project TEXT PRIMARY KEY, version TEXT NOT NULL);
    CREATE TABLE typo3_latest (major TEXT PRIMARY KEY, version TEXT NOT NULL);
    CREATE TABLE mail_watch (pipeline INTEGER PRIMARY KEY, project TEXT NOT NULL, web_url TEXT, trigger TEXT, t TEXT);
    CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # version 2: config.json -> projects (one row per project, settings as JSON, list order in position) + settings
    """
    CREATE TABLE projects (id TEXT PRIMARY KEY, position INTEGER NOT NULL, data TEXT NOT NULL);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # version 3: login (users managed on the command line, sessions store only a hash of the cookie token)
    """
    CREATE TABLE users (name TEXT PRIMARY KEY, hash TEXT NOT NULL, created TEXT NOT NULL);
    CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, user TEXT NOT NULL REFERENCES users (name) ON DELETE CASCADE,
        expires INTEGER NOT NULL);
    CREATE INDEX sessions_user ON sessions (user);
    """,
    # version 4: account lock after failed logins (unlocked only on the command line)
    """
    ALTER TABLE users ADD COLUMN failed INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE users ADD COLUMN locked TEXT;
    """,
    # version 5: basic profile fields, edited by the user on the Profile page
    """
    ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT '';
    ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT '';
    """,
]
CONFIG_DEFAULTS = {"port": 8787, "check_interval_hours": 6}

_lock = threading.RLock()
_conn = None


def _connect():
    global _conn
    if _conn is None:
        if not DB_FILE.exists():
            os.close(os.open(DB_FILE, os.O_WRONLY | os.O_CREAT, 0o600))
        os.chmod(DB_FILE, 0o600)
        c = sqlite3.connect(DB_FILE, check_same_thread=False, isolation_level=None, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        _migrate(c)
        _conn = c
    return _conn


def close():
    """Close the shared connection (Gunicorn master: never hand an open SQLite connection to a forked worker)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


@contextlib.contextmanager
def tx():
    """Transaction (BEGIN IMMEDIATE … COMMIT, ROLLBACK on error); yields the connection."""
    with _lock:
        c = _connect()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")


def _rows(sql, args=()):
    with _lock:
        return [dict(r) for r in _connect().execute(sql, args)]


def _migrate(c):
    version = c.execute("PRAGMA user_version").fetchone()[0]
    imports = {0: (_import_state, STATE), 1: (_import_config, CONFIG)}    # schema index -> (import, file it replaces)
    imported = []
    for i in range(version, len(SCHEMA)):
        c.execute("BEGIN IMMEDIATE")
        try:
            # statement by statement: executescript() would COMMIT the open transaction
            for stmt in filter(str.strip, SCHEMA[i].split(";")):
                c.execute(stmt)
            fn, path = imports.get(i, (None, None))
            if path and path.exists():
                fn(c, json.loads(path.read_text(encoding="utf-8")))
                imported.append(path)
            c.execute(f"PRAGMA user_version = {i + 1}")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        c.execute("COMMIT")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    for path in imported:                   # only after the commit: a failed import leaves the file in place
        os.replace(path, path.with_name(f"{path.name}.imported-{stamp}"))


def _import_state(c, st):
    # lists are stored newest first -> insert oldest first so the ids keep the order
    c.executemany("INSERT INTO log (t, msg) VALUES (?, ?)",
                  [(x.get("t", ""), x.get("msg", "")) for x in reversed(st.get("log", []))])
    c.executemany("INSERT INTO runs (t, project, pipeline, web_url, trigger, ref) VALUES (?, ?, ?, ?, ?, ?)",
                  [(r.get("t", ""), r["project"], int(r["pipeline"]), r.get("web_url"), r.get("trigger"), r.get("ref"))
                   for r in reversed(st.get("runs", []))])
    c.executemany("INSERT INTO scheduler (task, last_run, finished, ok, result) VALUES (?, ?, ?, ?, ?)",
                  [(k, v.get("last_run"), v.get("finished"), None if v.get("ok") is None else int(bool(v["ok"])),
                    v.get("result")) for k, v in (st.get("scheduler") or {}).items()])
    for table, key in (("typo3_seen", "typo3_seen"), ("typo3_announced", "typo3_announced")):
        c.executemany(f"INSERT INTO {table} (project, version) VALUES (?, ?)", list((st.get(key) or {}).items()))
    c.executemany("INSERT INTO typo3_latest (major, version) VALUES (?, ?)",
                  [(str(k), v) for k, v in (st.get("typo3_latest") or {}).items()])
    c.executemany("INSERT OR REPLACE INTO mail_watch (pipeline, project, web_url, trigger, t) VALUES (?, ?, ?, ?, ?)",
                  [(int(w["pipeline"]), w["project"], w.get("web_url"), w.get("trigger"), w.get("t"))
                   for w in st.get("mail_watch", [])])
    # projects whose runs were already trimmed away in state.json (only 100 runs were kept there)
    for key in ("last_check", "typo3_security", "projects_with_runs"):
        if st.get(key) is not None:
            c.execute("INSERT INTO kv (key, value) VALUES (?, ?)",
                      ("projects_with_runs_imported" if key == "projects_with_runs" else key, json.dumps(st[key])))


def _import_config(c, cfg):
    _write_config(c, cfg)


def _write_config(c, cfg):
    projects = cfg.get("projects") or []
    ids = [p["id"] for p in projects]
    if len(set(ids)) != len(ids):
        raise RuntimeError("Duplicate project ids")
    c.execute(f"DELETE FROM projects WHERE id NOT IN ({','.join('?' * len(ids))})", ids)
    c.executemany("INSERT INTO projects (id, position, data) VALUES (?, ?, ?) ON CONFLICT (id) DO UPDATE "
                  "SET position = excluded.position, data = excluded.data",
                  [(p["id"], i, json.dumps(p, ensure_ascii=False)) for i, p in enumerate(projects)])
    settings = {k: v for k, v in cfg.items() if k != "projects"}
    c.execute(f"DELETE FROM settings WHERE key NOT IN ({','.join('?' * len(settings))})", list(settings))
    c.executemany("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                  [(k, json.dumps(v, ensure_ascii=False)) for k, v in settings.items()])


# ---------------------------------------------------------------- configuration (projects + settings)
def load_config():
    """Same shape as the former config.json: {setting: value, …, "projects": [project, …]} (project order kept)."""
    with _lock:
        c = _connect()
        cfg = {**CONFIG_DEFAULTS, **{r["key"]: json.loads(r["value"]) for r in c.execute("SELECT key, value FROM settings")}}
        cfg["projects"] = [json.loads(r["data"]) for r in c.execute("SELECT data FROM projects ORDER BY position")]
    return cfg


def save_config(cfg):
    """Replace projects and settings with cfg (one transaction). Callers hold core.lock for read-modify-write."""
    with tx() as c:
        _write_config(c, cfg)


# ---------------------------------------------------------------- key/value (small JSON values)
def kv_get(key, default=None):
    r = _rows("SELECT value FROM kv WHERE key = ?", (key,))
    return json.loads(r[0]["value"]) if r else default


def kv_set(key, value):
    with tx() as c:
        c.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                  (key, json.dumps(value, ensure_ascii=False)))


# ---------------------------------------------------------------- log
def log_add(t, msg):
    with tx() as c:
        cur = c.execute("INSERT INTO log (t, msg) VALUES (?, ?)", (t, msg))
        if cur.lastrowid % 100 == 0:
            c.execute("DELETE FROM log WHERE id <= ?", (cur.lastrowid - LOG_KEEP,))


def log_recent(limit=50):
    return _rows("SELECT t, msg FROM log ORDER BY id DESC LIMIT ?", (limit,))


# ---------------------------------------------------------------- runs (all kept)
def run_add(run):
    with tx() as c:
        c.execute("INSERT INTO runs (t, project, pipeline, web_url, trigger, ref) VALUES (?, ?, ?, ?, ?, ?)",
                  (run["t"], run["project"], int(run["pipeline"]), run.get("web_url"), run.get("trigger"), run.get("ref")))


def runs_recent(limit=30):
    return _rows("SELECT t, project, pipeline, web_url, trigger, ref FROM runs ORDER BY id DESC LIMIT ?", (limit,))


def last_pipelines():
    """{project id: pipeline id of its newest run}"""
    return {r["project"]: r["pipeline"] for r in
            _rows("SELECT project, pipeline FROM runs WHERE id IN (SELECT MAX(id) FROM runs GROUP BY project)")}


def projects_with_runs():
    ids = {r["project"] for r in _rows("SELECT DISTINCT project FROM runs")}
    return sorted(ids | set(kv_get("projects_with_runs_imported", [])))


# ---------------------------------------------------------------- scheduler results
def sched_results():
    return {r.pop("task"): {**r, "ok": None if r["ok"] is None else bool(r["ok"])}
            for r in _rows("SELECT task, last_run, finished, ok, result FROM scheduler")}


def sched_result_set(task, last_run, finished, ok, result):
    with tx() as c:
        c.execute("""INSERT INTO scheduler (task, last_run, finished, ok, result) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (task) DO UPDATE SET last_run = excluded.last_run, finished = excluded.finished,
            ok = excluded.ok, result = excluded.result""", (task, last_run, finished, int(bool(ok)), result))


# ---------------------------------------------------------------- TYPO3 versions
def typo3_seen():
    return {r["project"]: r["version"] for r in _rows("SELECT project, version FROM typo3_seen")}


def typo3_seen_set(project, version):
    with tx() as c:
        c.execute("INSERT INTO typo3_seen (project, version) VALUES (?, ?) "
                  "ON CONFLICT (project) DO UPDATE SET version = excluded.version", (project, version))


def typo3_seen_reset(projects):
    """Forget the baseline (next check stores a new one, no trigger)."""
    with tx() as c:
        c.executemany("DELETE FROM typo3_seen WHERE project = ?", [(p,) for p in projects])


def typo3_announce(items):
    """items: [(project id, version)]; marks them announced and returns the ones not announced before."""
    with tx() as c:
        done = {r["project"]: r["version"] for r in c.execute("SELECT project, version FROM typo3_announced")}
        todo = [(p, v) for p, v in items if done.get(p) != v]
        c.executemany("INSERT INTO typo3_announced (project, version) VALUES (?, ?) "
                      "ON CONFLICT (project) DO UPDATE SET version = excluded.version", todo)
    return todo


def typo3_latest():
    return {r["major"]: r["version"] for r in _rows("SELECT major, version FROM typo3_latest")}


def typo3_latest_merge(latest):
    """Update the given majors; majors whose check failed keep their last known version."""
    with tx() as c:
        c.executemany("INSERT INTO typo3_latest (major, version) VALUES (?, ?) "
                      "ON CONFLICT (major) DO UPDATE SET version = excluded.version",
                      [(str(k), v) for k, v in latest.items()])


# ---------------------------------------------------------------- pending e-mail notifications
def mail_watch_add(w):
    with tx() as c:
        c.execute("INSERT OR REPLACE INTO mail_watch (pipeline, project, web_url, trigger, t) VALUES (?, ?, ?, ?, ?)",
                  (int(w["pipeline"]), w["project"], w.get("web_url"), w.get("trigger"), w.get("t")))


def mail_watch_done(pipeline):
    with tx() as c:
        c.execute("DELETE FROM mail_watch WHERE pipeline = ?", (int(pipeline),))


def mail_watches():
    return _rows("SELECT project, pipeline, web_url, trigger, t FROM mail_watch ORDER BY t")


# ---------------------------------------------------------------- users and sessions (login, see auth.py)
def user_get(name):
    r = _rows("SELECT name, hash, failed, locked FROM users WHERE name = ?", (name,))
    return r[0] if r else None


def users():
    return _rows("SELECT name, created, locked FROM users ORDER BY name")


def user_add(name, pw_hash):
    with tx() as c:
        c.execute("INSERT INTO users (name, hash, created) VALUES (?, ?, ?)",
                  (name, pw_hash, datetime.datetime.now().isoformat(timespec="seconds")))


def user_set_hash(name, pw_hash):
    with tx() as c:
        return c.execute("UPDATE users SET hash = ? WHERE name = ?", (pw_hash, name)).rowcount > 0


def user_fail(name, max_failed):
    """Count a failed login; lock the account at max_failed. -> True if the account is locked now."""
    with tx() as c:
        c.execute("UPDATE users SET failed = failed + 1, locked = CASE WHEN failed + 1 >= ? AND locked IS NULL "
                  "THEN ? ELSE locked END WHERE name = ?",
                  (max_failed, datetime.datetime.now().isoformat(timespec="seconds"), name))
        r = c.execute("SELECT locked FROM users WHERE name = ?", (name,)).fetchone()
        return bool(r and r["locked"])


def user_reset_failed(name):
    """Successful login or unlock: counter to 0, lock removed. -> False if the user does not exist."""
    with tx() as c:
        return c.execute("UPDATE users SET failed = 0, locked = NULL WHERE name = ?", (name,)).rowcount > 0


def user_profile(name):
    r = _rows("SELECT name, full_name, email, created FROM users WHERE name = ?", (name,))
    return r[0] if r else None


def user_profile_set(name, full_name, email):
    with tx() as c:
        c.execute("UPDATE users SET full_name = ?, email = ? WHERE name = ?", (full_name, email, name))


def user_delete(name):
    with tx() as c:
        return c.execute("DELETE FROM users WHERE name = ?", (name,)).rowcount > 0


def session_add(token_hash, user, expires):
    with tx() as c:
        c.execute("DELETE FROM sessions WHERE expires < strftime('%s', 'now')")
        c.execute("INSERT INTO sessions (token_hash, user, expires) VALUES (?, ?, ?)", (token_hash, user, expires))


def session_user(token_hash, now_ts):
    r = _rows("SELECT user FROM sessions WHERE token_hash = ? AND expires > ?", (token_hash, now_ts))
    return r[0]["user"] if r else None


def session_delete(token_hash):
    with tx() as c:
        c.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))


def sessions_delete_user(user, keep=None):
    """All sessions of a user, except the one with token hash `keep`."""
    with tx() as c:
        c.execute("DELETE FROM sessions WHERE user = ? AND token_hash IS NOT ?", (user, keep))
