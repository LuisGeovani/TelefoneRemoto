"""Persistent single-admin authentication with local bootstrap recovery."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

SESSION_COOKIE = "s10_control_session"
PASSWORD_SCHEME = "scrypt-n16384-r8-p1"
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


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


class AuthError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Principal:
    session_id: str
    user_name: str
    role: str
    csrf_token: str


@dataclass(frozen=True)
class AccountStatus:
    configured: bool
    username: str | None


class AuthService:
    def __init__(self, connection: sqlite3.Connection, settings: Settings):
        self.connection = connection
        self.settings = settings
        self._lock = threading.RLock()
        self._dummy_salt = secrets.token_bytes(16)

    def account_status(self) -> AccountStatus:
        with self._lock:
            row = self.connection.execute("SELECT username FROM admin_account WHERE id = 1").fetchone()
        return AccountStatus(row is not None, str(row["username"]) if row else None)

    def has_account(self) -> bool:
        return self.account_status().configured

    def ensure_bootstrap(self, lifetime_seconds: int = 15 * 60, force: bool = False) -> str | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT consumed_at, expires_at FROM bootstrap_credentials WHERE id = 1"
            ).fetchone()
            if (
                not force
                and row
                and row["consumed_at"] is None
                and row["expires_at"] > _now()
                and self.settings.bootstrap_path.exists()
            ):
                return None
            token = _encode_secret()
            salt = secrets.token_bytes(16)
            now = _now()
            with self.connection:
                self.connection.execute("DELETE FROM bootstrap_credentials")
                self.connection.execute(
                    "INSERT INTO bootstrap_credentials (id, salt, digest, expires_at, consumed_at) VALUES (1, ?, ?, ?, NULL)",
                    (salt, _digest(token, salt), now + lifetime_seconds),
                )
                if force:
                    account = self.connection.execute(
                        "SELECT auth_version FROM admin_account WHERE id = 1"
                    ).fetchone()
                    if account:
                        self.connection.execute(
                            "UPDATE admin_account SET auth_version = auth_version + 1, updated_at = ? WHERE id = 1",
                            (now,),
                        )
                    self.connection.execute(
                        "UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL", (now,)
                    )
            _write_private(self.settings.bootstrap_path, token)
            return token

    def local_bootstrap_token(self) -> str:
        self.ensure_bootstrap()
        try:
            return self.settings.bootstrap_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as error:
            raise RuntimeError("bootstrap token is unavailable; run 's10-control auth reset --yes' locally") from error

    def _bootstrap_row(self, token: str) -> sqlite3.Row | None:
        row = self.connection.execute(
            "SELECT salt, digest, expires_at, consumed_at FROM bootstrap_credentials WHERE id = 1"
        ).fetchone()
        if not row or row["consumed_at"] is not None or row["expires_at"] <= _now():
            return None
        try:
            matches = hmac.compare_digest(_digest(token, row["salt"]), row["digest"])
        except (TypeError, ValueError):
            return None
        return row if matches else None

    @staticmethod
    def _validate_username(username: str) -> None:
        allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
        if not 1 <= len(username) <= 64 or any(character not in allowed for character in username):
            raise AuthError("INVALID_USERNAME")

    @staticmethod
    def _validate_password(password: str) -> None:
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            raise AuthError("INVALID_PASSWORD_POLICY")

    def setup_account(self, token: str, username: str, password: str) -> Principal:
        self._validate_username(username)
        self._validate_password(password)
        with self._lock:
            if self.connection.execute("SELECT 1 FROM admin_account WHERE id = 1").fetchone():
                raise AuthError("ACCOUNT_ALREADY_CONFIGURED")
            if self._bootstrap_row(token) is None:
                raise AuthError("INVALID_BOOTSTRAP")
            salt = secrets.token_bytes(16)
            now = _now()
            with self.connection:
                self.connection.execute(
                    "INSERT INTO admin_account "
                    "(id, username, password_scheme, password_salt, password_digest, auth_version, created_at, updated_at) "
                    "VALUES (1, ?, ?, ?, ?, 1, ?, ?)",
                    (username, PASSWORD_SCHEME, salt, _digest(password, salt), now, now),
                )
                self.connection.execute(
                    "UPDATE bootstrap_credentials SET consumed_at = ? WHERE id = 1", (now,)
                )
            self.settings.bootstrap_path.unlink(missing_ok=True)
            return self.create_session()

    def authenticate(self, username: str, password: str) -> Principal | None:
        with self._lock:
            row = self.connection.execute(
                "SELECT username, password_scheme, password_salt, password_digest FROM admin_account WHERE id = 1"
            ).fetchone()
            salt = row["password_salt"] if row else self._dummy_salt
            candidate = _digest(password, salt)
            if not row or row["password_scheme"] != PASSWORD_SCHEME:
                return None
            username_matches = hmac.compare_digest(
                username.encode("utf-8"), str(row["username"]).encode("utf-8")
            )
            password_matches = hmac.compare_digest(candidate, row["password_digest"])
            if not username_matches or not password_matches:
                return None
            return self.create_session()

    def recover_account(self, token: str, password: str) -> Principal:
        self._validate_password(password)
        with self._lock:
            account = self.connection.execute(
                "SELECT auth_version FROM admin_account WHERE id = 1"
            ).fetchone()
            if not account:
                raise AuthError("ACCOUNT_NOT_CONFIGURED")
            if self._bootstrap_row(token) is None:
                raise AuthError("INVALID_BOOTSTRAP")
            salt = secrets.token_bytes(16)
            now = _now()
            with self.connection:
                self.connection.execute(
                    "UPDATE admin_account SET password_scheme = ?, password_salt = ?, password_digest = ?, "
                    "auth_version = auth_version + 1, updated_at = ? WHERE id = 1",
                    (PASSWORD_SCHEME, salt, _digest(password, salt), now),
                )
                self.connection.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE revoked_at IS NULL", (now,)
                )
                self.connection.execute(
                    "UPDATE bootstrap_credentials SET consumed_at = ? WHERE id = 1", (now,)
                )
            self.settings.bootstrap_path.unlink(missing_ok=True)
            return self.create_session()

    def create_session(self) -> Principal:
        with self._lock:
            account = self.connection.execute(
                "SELECT username, auth_version FROM admin_account WHERE id = 1"
            ).fetchone()
            if not account:
                raise AuthError("ACCOUNT_NOT_CONFIGURED")
            identifier = str(uuid.uuid4())
            secret = _encode_secret()
            salt = secrets.token_bytes(16)
            csrf = _encode_secret()
            now = _now()
            with self.connection:
                self.connection.execute(
                    "DELETE FROM sessions WHERE expires_at <= ? OR revoked_at IS NOT NULL", (now,)
                )
                self.connection.execute(
                    "INSERT INTO sessions "
                    "(id, user_name, role, salt, digest, csrf_token, auth_version, created_at, expires_at, revoked_at) "
                    "VALUES (?, ?, 'admin', ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        identifier,
                        account["username"],
                        salt,
                        _digest(secret, salt),
                        csrf,
                        account["auth_version"],
                        now,
                        now + self.settings.session_ttl_hours * 3600,
                    ),
                )
            return Principal(f"{identifier}.{secret}", str(account["username"]), "admin", csrf)

    def principal_for_cookie(self, cookie: str | None) -> Principal | None:
        if not cookie or "." not in cookie:
            return None
        identifier, secret = cookie.split(".", 1)
        with self._lock:
            row = self.connection.execute(
                "SELECT s.salt, s.digest, s.csrf_token, s.auth_version, s.expires_at, s.revoked_at, "
                "a.username AS current_username, a.auth_version AS current_auth_version "
                "FROM sessions s JOIN admin_account a ON a.id = 1 WHERE s.id = ?",
                (identifier,),
            ).fetchone()
            if (
                not row
                or row["revoked_at"] is not None
                or row["expires_at"] <= _now()
                or row["auth_version"] != row["current_auth_version"]
            ):
                return None
            if not hmac.compare_digest(_digest(secret, row["salt"]), row["digest"]):
                return None
            return Principal(cookie, str(row["current_username"]), "admin", str(row["csrf_token"]))

    def is_session_active(self, session_id: str) -> bool:
        return self.active_session_role(session_id) is not None

    def active_session_role(self, session_id: str) -> str | None:
        identifier = session_id.split(".", 1)[0]
        with self._lock:
            row = self.connection.execute(
                "SELECT s.role, s.expires_at, s.revoked_at, s.auth_version, a.auth_version AS current_auth_version "
                "FROM sessions s JOIN admin_account a ON a.id = 1 WHERE s.id = ?",
                (identifier,),
            ).fetchone()
        if (
            not row
            or row["revoked_at"] is not None
            or row["expires_at"] <= _now()
            or row["auth_version"] != row["current_auth_version"]
        ):
            return None
        return str(row["role"])

    def revoke(self, session_id: str) -> None:
        identifier = session_id.split(".", 1)[0]
        with self._lock, self.connection:
            self.connection.execute("UPDATE sessions SET revoked_at = ? WHERE id = ?", (_now(), identifier))
