"""Login: named users (scrypt password hash) and server-side sessions, stored in SQLite (stdlib only).

Users are managed on the command line (bin/t3-watchdock add-user NAME); the browser only signs in and out.
The session cookie holds a random token; the database keeps only its SHA-256 hash.
"""
import hashlib
import hmac
import re
import secrets
import threading
import time

from . import db
from .core import log

SESSION_HOURS = 12                      # absolute session lifetime
COOKIE = "wd_session"
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
NAME_RE = re.compile(r"^[A-Za-z0-9._@-]{1,64}$")
MIN_PASSWORD = 12
LOCK_AFTER = 3                          # failed logins in a row -> account locked until unlock-user (CLI)
FAIL_MAX, FAIL_WINDOW = 5, 15 * 60      # failed logins per client address and window (seconds), any name
LOCKED_MSG = (f"Account locked after {LOCK_AFTER} failed logins. "
              "An admin must unlock it on the command line (t3-watchdock unlock-user NAME).")

_fails = {}
_fails_lock = threading.Lock()


# ---------------------------------------------------------------- passwords
def hash_password(password):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return f"scrypt${SCRYPT['n']}${SCRYPT['r']}${SCRYPT['p']}${salt.hex()}${h.hex()}"


def _check(stored, password):
    _, n, r, p, salt, h = stored.split("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(h) // 2)
    return hmac.compare_digest(got.hex(), h)


_DUMMY = hash_password(secrets.token_hex(16))   # unknown user: same work as a real check (no timing hint)


# ---------------------------------------------------------------- users (CLI)
def check_name(name):
    if not NAME_RE.match(name or ""):
        raise ValueError("Name: 1-64 characters, letters, digits and . _ @ - only")


def check_password(password):
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password needs at least {MIN_PASSWORD} characters")


def add_user(name, password):
    check_name(name)
    check_password(password)
    if db.user_get(name):
        raise ValueError(f"User exists: {name} (change the password with set-password)")
    db.user_add(name, hash_password(password))


def set_password(name, password):
    check_password(password)
    if not db.user_set_hash(name, hash_password(password)):
        raise ValueError(f"No such user: {name}")
    db.user_reset_failed(name)           # a new password also unlocks the account
    db.sessions_delete_user(name)        # sign out everywhere


def change_password(name, current, new, keep_token):
    """Own password change from the browser: current password required; other sessions end, this one stays."""
    u = db.user_get(name)
    if not u or u["locked"]:
        raise PermissionError(LOCKED_MSG)
    if not _check(u["hash"], current or ""):
        if db.user_fail(name, LOCK_AFTER):
            db.sessions_delete_user(name)
            log(f"Account locked after {LOCK_AFTER} failed logins: {name}")
            raise PermissionError(LOCKED_MSG)
        raise PermissionError("Current password is wrong")
    check_password(new or "")
    db.user_set_hash(name, hash_password(new))
    db.user_reset_failed(name)
    db.sessions_delete_user(name, keep=_digest(keep_token))
    log(f"Password changed in the browser: {name}")


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def update_profile(name, full_name, email):
    full_name, email = (full_name or "").strip(), (email or "").strip()
    if len(full_name) > 100:
        raise ValueError("Full name: at most 100 characters")
    if email and (len(email) > 254 or not EMAIL_RE.match(email)):
        raise ValueError("Email address is not valid")
    db.user_profile_set(name, full_name, email)
    return db.user_profile(name)


def unlock_user(name):
    if not db.user_reset_failed(name):
        raise ValueError(f"No such user: {name}")
    log(f"Account unlocked on the command line: {name}")


def remove_user(name):
    if not db.user_delete(name):         # sessions go with it (ON DELETE CASCADE)
        raise ValueError(f"No such user: {name}")


# ---------------------------------------------------------------- login / sessions
def _limited(addr):
    with _fails_lock:
        cut = time.time() - FAIL_WINDOW
        _fails[addr] = [t for t in _fails.get(addr, []) if t > cut]
        return len(_fails[addr]) >= FAIL_MAX


def _fail(addr):
    with _fails_lock:
        _fails.setdefault(addr, []).append(time.time())


def login(name, password, addr):
    """-> (session token, max age in seconds); raises PermissionError."""
    if _limited(addr):
        raise PermissionError("Too many failed logins, try again later")
    u = db.user_get(name or "")
    if u and u["locked"]:
        raise PermissionError(LOCKED_MSG)
    if not _check(u["hash"] if u else _DUMMY, password or "") or not u:
        _fail(addr)
        if u and db.user_fail(u["name"], LOCK_AFTER):
            db.sessions_delete_user(u["name"])           # locked = signed out everywhere
            log(f"Account locked after {LOCK_AFTER} failed logins: {u['name']}")
            raise PermissionError(LOCKED_MSG)
        raise PermissionError("Wrong name or password")
    with _fails_lock:
        _fails.pop(addr, None)
    if u["failed"]:
        db.user_reset_failed(u["name"])
    token = secrets.token_urlsafe(32)
    db.session_add(_digest(token), u["name"], int(time.time()) + SESSION_HOURS * 3600)
    return token, SESSION_HOURS * 3600


def session_user(token):
    """User name of a valid session token, else None."""
    return db.session_user(_digest(token), int(time.time())) if token else None


def logout(token):
    if token:
        db.session_delete(_digest(token))


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()
