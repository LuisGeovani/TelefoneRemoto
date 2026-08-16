"""Bootstrap and cookie-session authentication with local recovery only."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

SESSION_COOKIE = "s10_control_session"


def _now() -> int:
    return int(time.time())


def _encode_secret() -> str:
    return secrets.token_urlsafe(32)


def _digest(secret: str, salt: bytes) -> bytes:
    return hashlib.scrypt(secret.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        path.chmod(0o600)


@dataclass(frozen=True)
class Principal:
    session_id: str
    user_name: str
    role: str
    csrf_token: str


class AuthService:
    def __init__(self, connection: sqlite3.Connection, settings: Settings):
        self.connection = connection
        self.settings = settings

    def ensure_bootstrap(self, lifetime_seconds: int = 15 * 60, force: bool = False) -> str | None:
        row = self.connection.execute("SELECT consumed_at, expires_at FROM bootstrap_credentials WHERE id = 1").fetchone()
        if not force and row and row["consumed_at"] is None and row["expires_at"] > _now() and self.settings.bootstrap_path.exists():
            return None
        token = _encode_secret()
        salt = secrets.token_bytes(16)
        with self.connection:
            self.connection.execute("DELETE FROM bootstrap_credentials")
            self.connection.execute(
                "INSERT INTO bootstrap_credentials (id, salt, digest, expires_at, consumed_at) VALUES (1, ?, ?, ?, NULL)",
                (salt, _digest(token, salt), _now() + lifetime_seconds),
            )
            self.connection.execute("UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL", (_now(),))
        _write_private(self.settings.bootstrap_path, token)
        return token

    def local_bootstrap_token(self) -> str:
        self.ensure_bootstrap()
        try:
            return self.settings.bootstrap_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as error:
            raise RuntimeError("bootstrap token is already consumed; run 's10-control auth reset' locally") from error

    def exchange_bootstrap(self, token: str) -> Principal | None:
        row = self.connection.execute("SELECT salt, digest, expires_at, consumed_at FROM bootstrap_credentials WHERE id = 1").fetchone()
        if not row or row["consumed_at"] is not None or row["expires_at"] <= _now():
            return None
        if not hmac.compare_digest(_digest(token, row["salt"]), row["digest"]):
            return None
        with self.connection:
            self.connection.execute("UPDATE bootstrap_credentials SET consumed_at = ? WHERE id = 1", (_now(),))
        self.settings.bootstrap_path.unlink(missing_ok=True)
        return self.create_session("admin", "admin")

    def create_session(self, user_name: str, role: str) -> Principal:
        identifier = str(uuid.uuid4())
        secret = _encode_secret()
        salt = secrets.token_bytes(16)
        csrf = _encode_secret()
        now = _now()
        with self.connection:
            self.connection.execute(
                "INSERT INTO sessions (id, user_name, role, salt, digest, csrf_token, created_at, expires_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (identifier, user_name, role, salt, _digest(secret, salt), csrf, now, now + self.settings.session_ttl_hours * 3600),
            )
        return Principal(f"{identifier}.{secret}", user_name, role, csrf)

    def principal_for_cookie(self, cookie: str | None) -> Principal | None:
        if not cookie or "." not in cookie:
            return None
        identifier, secret = cookie.split(".", 1)
        row = self.connection.execute(
            "SELECT id, user_name, role, salt, digest, csrf_token, expires_at, revoked_at FROM sessions WHERE id = ?", (identifier,)
        ).fetchone()
        if not row or row["revoked_at"] is not None or row["expires_at"] <= _now():
            return None
        if not hmac.compare_digest(_digest(secret, row["salt"]), row["digest"]):
            return None
        return Principal(cookie, row["user_name"], row["role"], row["csrf_token"])

    def revoke(self, session_id: str) -> None:
        identifier = session_id.split(".", 1)[0]
        with self.connection:
            self.connection.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (_now(), identifier))
