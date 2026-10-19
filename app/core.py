"""Общие части: настройки, база данных, пароли. Используется сервисом и CLI."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIR = Path(os.environ.get("PD_DATA_DIR", "/srv/pdfdisplay"))
FILES_DIR = DATA_DIR / "files"
DB_PATH = DATA_DIR / "db" / "pdfdisplay.db"
PDFJS_DIR = Path(os.environ.get("PD_PDFJS_DIR", "/opt/pdfdisplay/pdfjs"))
PUBLIC_URL = os.environ.get("PD_PUBLIC_URL", "http://localhost:8000").rstrip("/")
PUBLIC_HOST = urlsplit(PUBLIC_URL).netloc
MAX_FILE_BYTES = int(os.environ.get("PD_MAX_FILE_MB", "2048")) * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT    PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS folders (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL UNIQUE,
    quota_bytes  INTEGER,
    allow_direct INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS folder_domains (
    folder_id INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    domain    TEXT    NOT NULL,
    PRIMARY KEY (folder_id, domain)
);
CREATE TABLE IF NOT EXISTS files (
    id         TEXT    PRIMARY KEY,
    folder_id  INTEGER NOT NULL REFERENCES folders(id),
    name       TEXT    NOT NULL,
    size       INTEGER NOT NULL,
    sha256     TEXT    NOT NULL,
    mime       TEXT    NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS files_folder ON files(folder_id);
"""


def now() -> int:
    return int(time.time())


def connect() -> sqlite3.Connection:
    # isolation_level=None: автокоммит, транзакции открываем явно через transaction().
    conn = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


_SCRYPT = {"n": 2**15, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r),
                              p=int(p), maxmem=64 * 1024 * 1024)
    except ValueError:
        return False
    return hmac.compare_digest(calc.hex(), digest)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
