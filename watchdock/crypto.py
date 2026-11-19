"""Encryption of stored secrets (GitLab tokens) with Fernet from the `cryptography` package (AES-CBC + HMAC-SHA256).

The key is kept outside the data folder, so a copy of watchdock.db or a backup alone does not reveal the tokens.
Key source, first match wins:
  1. WATCHDOCK_SECRET_KEY        the key itself (env variable, e.g. from compose .env)
  2. WATCHDOCK_SECRET_KEY_FILE   path to a file holding the key (e.g. a Docker secret)
  3. ~/.t3-watchdock-secret-key  local start without 1 and 2: created on first use (mode 600)
New key: t3-watchdock gen-secret-key. A changed key makes stored tokens unreadable: they must be saved again.
"""
import functools
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

KEY_FILE_DEFAULT = Path.home() / ".t3-watchdock-secret-key"


def new_key():
    return Fernet.generate_key().decode()


def _read_key():
    env = os.environ.get("WATCHDOCK_SECRET_KEY", "").strip()
    if env:
        return env, "WATCHDOCK_SECRET_KEY"
    path = os.environ.get("WATCHDOCK_SECRET_KEY_FILE", "").strip()
    if path:
        return Path(path).read_text(encoding="utf-8").strip(), path
    if not KEY_FILE_DEFAULT.exists():
        fd = os.open(KEY_FILE_DEFAULT, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(new_key())
    return KEY_FILE_DEFAULT.read_text(encoding="utf-8").strip(), str(KEY_FILE_DEFAULT)


@functools.cache
def _fernet():
    key, source = _read_key()
    try:
        return Fernet(key.encode())
    except ValueError:
        raise RuntimeError(f"Secret key from {source} is not a valid key "
                           "(create one with: t3-watchdock gen-secret-key)") from None


def encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value):
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise RuntimeError("A stored GitLab token cannot be decrypted: the secret key has changed. "
                           "Save the token again.") from None
