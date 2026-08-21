import io
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from s10_control.auth import AuthError, AuthService, PASSWORD_SCHEME
from s10_control.cli import main
from s10_control.config import load_settings
from s10_control.database import open_database


USERNAME = "test-admin"
PASSWORD = "test-password-1234"
NEW_PASSWORD = "replacement-password-5678"


class AuthenticationTests(unittest.TestCase):
    def service(self, directory: str):
        settings = load_settings(Path(directory))
        connection = open_database(settings.database_path)
        return settings, connection, AuthService(connection, settings)

    def test_unconfigured_setup_is_one_time_and_password_is_only_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, connection, auth = self.service(directory)
            try:
                self.assertFalse(auth.account_status().configured)
                token = auth.ensure_bootstrap()
                self.assertIsNotNone(token)
                with self.assertRaisesRegex(AuthError, "INVALID_BOOTSTRAP"):
                    auth.setup_account("invalid-bootstrap-token-value", USERNAME, PASSWORD)

                principal = auth.setup_account(token or "", USERNAME, PASSWORD)
                self.assertTrue(auth.account_status().configured)
                self.assertEqual(auth.account_status().username, USERNAME)
                self.assertFalse(settings.bootstrap_path.exists())
                self.assertIsNotNone(auth.principal_for_cookie(principal.session_id))
                row = connection.execute(
                    "SELECT username, password_scheme, password_salt, password_digest, auth_version FROM admin_account"
                ).fetchone()
                self.assertEqual(row["username"], USERNAME)
                self.assertEqual(row["password_scheme"], PASSWORD_SCHEME)
                self.assertEqual(len(row["password_salt"]), 16)
                self.assertNotEqual(row["password_digest"], PASSWORD.encode("utf-8"))
                self.assertEqual(row["auth_version"], 1)
                self.assertNotIn(PASSWORD.encode("utf-8"), settings.database_path.read_bytes())

                second_token = auth.ensure_bootstrap()
                with self.assertRaisesRegex(AuthError, "ACCOUNT_ALREADY_CONFIGURED"):
                    auth.setup_account(second_token or "", "second-admin", NEW_PASSWORD)
            finally:
                connection.close()

    def test_login_session_persists_across_service_recreation_and_can_be_revoked(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, connection, auth = self.service(directory)
            token = auth.ensure_bootstrap()
            auth.setup_account(token or "", USERNAME, PASSWORD)
            self.assertIsNone(auth.authenticate("wrong-admin", PASSWORD))
            self.assertIsNone(auth.authenticate(USERNAME, "wrong-password"))
            principal = auth.authenticate(USERNAME, PASSWORD)
            self.assertIsNotNone(principal)
            cookie = principal.session_id
            connection.close()

            reopened = open_database(settings.database_path)
            try:
                recreated = AuthService(reopened, settings)
                self.assertEqual(recreated.principal_for_cookie(cookie).user_name, USERNAME)
                recreated.revoke(cookie)
                self.assertIsNone(recreated.principal_for_cookie(cookie))
            finally:
                reopened.close()

    def test_expiry_and_auth_version_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            _, connection, auth = self.service(directory)
            try:
                token = auth.ensure_bootstrap()
                principal = auth.setup_account(token or "", USERNAME, PASSWORD)
                identifier = principal.session_id.split(".", 1)[0]
                with connection:
                    connection.execute("UPDATE sessions SET expires_at = 0 WHERE id = ?", (identifier,))
                self.assertIsNone(auth.principal_for_cookie(principal.session_id))

                active = auth.authenticate(USERNAME, PASSWORD)
                with connection:
                    connection.execute("UPDATE admin_account SET auth_version = auth_version + 1 WHERE id = 1")
                self.assertIsNone(auth.principal_for_cookie(active.session_id))
            finally:
                connection.close()

    def test_recovery_changes_password_and_invalidates_old_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, connection, auth = self.service(directory)
            try:
                token = auth.ensure_bootstrap()
                old = auth.setup_account(token or "", USERNAME, PASSWORD)
                recovery_token = auth.local_bootstrap_token()
                self.assertIsNotNone(auth.principal_for_cookie(old.session_id))
                recovered = auth.recover_account(recovery_token, NEW_PASSWORD)
                self.assertIsNone(auth.principal_for_cookie(old.session_id))
                self.assertIsNotNone(auth.principal_for_cookie(recovered.session_id))
                self.assertIsNone(auth.authenticate(USERNAME, PASSWORD))
                self.assertIsNotNone(auth.authenticate(USERNAME, NEW_PASSWORD))
                self.assertFalse(settings.bootstrap_path.exists())
            finally:
                connection.close()

    def test_force_recovery_invalidates_sessions_but_plain_token_generation_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            _, connection, auth = self.service(directory)
            try:
                token = auth.ensure_bootstrap()
                principal = auth.setup_account(token or "", USERNAME, PASSWORD)
                auth.local_bootstrap_token()
                self.assertIsNotNone(auth.principal_for_cookie(principal.session_id))
                forced = auth.ensure_bootstrap(force=True)
                self.assertIsNotNone(forced)
                self.assertIsNone(auth.principal_for_cookie(principal.session_id))
            finally:
                connection.close()

    @unittest.skipIf(os.name == "nt", "POSIX permission bits are not meaningful on Windows")
    def test_database_and_bootstrap_are_private_on_posix(self):
        with tempfile.TemporaryDirectory() as directory:
            settings, connection, auth = self.service(directory)
            try:
                auth.ensure_bootstrap()
                self.assertEqual(settings.database_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(settings.bootstrap_path.stat().st_mode & 0o777, 0o600)
            finally:
                connection.close()

    def test_cli_status_and_reset_never_print_hashes_or_session_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"S10_CONTROL_DATA_DIR": directory}):
                settings = load_settings()
                connection = open_database(settings.database_path)
                auth = AuthService(connection, settings)
                token = auth.ensure_bootstrap()
                auth.setup_account(token or "", USERNAME, PASSWORD)
                connection.close()

                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["auth", "status"]), 0)
                status = output.getvalue()
                self.assertEqual(status, f"configured: true\nusername: {USERNAME}\n")
                self.assertNotIn("hash", status.lower())
                self.assertNotIn("session", status.lower())

                reset_output = io.StringIO()
                with redirect_stdout(reset_output):
                    self.assertEqual(main(["auth", "reset", "--yes"]), 0)
                self.assertGreaterEqual(len(reset_output.getvalue().strip()), 20)

    def test_existing_session_schema_is_migrated_without_replacing_the_database(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "s10-control.sqlite3"
            legacy = sqlite3.connect(database_path)
            legacy.executescript(
                """
                CREATE TABLE sessions (
                  id TEXT PRIMARY KEY,
                  user_name TEXT NOT NULL,
                  role TEXT NOT NULL,
                  salt BLOB NOT NULL,
                  digest BLOB NOT NULL,
                  csrf_token TEXT NOT NULL,
                  created_at INTEGER NOT NULL,
                  expires_at INTEGER NOT NULL,
                  revoked_at INTEGER
                );
                INSERT INTO sessions VALUES (
                  'legacy-id', 'admin', 'admin', X'00', X'00', 'legacy-csrf', 1, 2, NULL
                );
                """
            )
            legacy.commit()
            legacy.close()

            migrated = open_database(database_path)
            try:
                columns = {row[1] for row in migrated.execute("PRAGMA table_info(sessions)")}
                self.assertIn("auth_version", columns)
                row = migrated.execute(
                    "SELECT id, auth_version FROM sessions WHERE id = 'legacy-id'"
                ).fetchone()
                self.assertEqual((row["id"], row["auth_version"]), ("legacy-id", 0))
            finally:
                migrated.close()
