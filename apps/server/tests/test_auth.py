import tempfile
import unittest
from pathlib import Path

from s10_control.auth import AuthService
from s10_control.config import load_settings
from s10_control.database import open_database


class AuthenticationTests(unittest.TestCase):
    def test_bootstrap_is_one_time_and_session_is_revocable(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            connection = open_database(settings.database_path)
            try:
                auth = AuthService(connection, settings)
                token = auth.ensure_bootstrap()
                self.assertIsNotNone(token)
                principal = auth.exchange_bootstrap(token or "")
                self.assertIsNotNone(principal)
                self.assertIsNone(auth.exchange_bootstrap(token or ""))
                self.assertIsNotNone(auth.principal_for_cookie(principal.session_id))
                reset_token = auth.ensure_bootstrap(force=True)
                self.assertIsNotNone(reset_token)
                self.assertIsNone(auth.principal_for_cookie(principal.session_id))
            finally:
                connection.close()
