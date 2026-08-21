"""Small private SQLite store. It only stores credential/token hashes."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS bootstrap_credentials (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  salt BLOB NOT NULL,
  digest BLOB NOT NULL,
  expires_at INTEGER NOT NULL,
  consumed_at INTEGER
);
CREATE TABLE IF NOT EXISTS admin_account (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  username TEXT NOT NULL,
  password_scheme TEXT NOT NULL,
  password_salt BLOB NOT NULL,
  password_digest BLOB NOT NULL,
  auth_version INTEGER NOT NULL CHECK (auth_version >= 1),
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  user_name TEXT NOT NULL,
  role TEXT NOT NULL,
  salt BLOB NOT NULL,
  digest BLOB NOT NULL,
  csrf_token TEXT NOT NULL,
  auth_version INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  expires_at INTEGER NOT NULL,
  revoked_at INTEGER
);
CREATE INDEX IF NOT EXISTS sessions_expires_at ON sessions(expires_at);
"""


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(sessions)")}
    if "auth_version" not in columns:
        connection.execute("ALTER TABLE sessions ADD COLUMN auth_version INTEGER NOT NULL DEFAULT 0")
    connection.commit()
    if os.name != "nt":
        path.chmod(0o600)
    return connection
