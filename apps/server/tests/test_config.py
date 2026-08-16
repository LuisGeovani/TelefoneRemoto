import json
import tempfile
import unittest
from pathlib import Path

from s10_control.config import ConfigurationError, load_settings


class ConfigurationTests(unittest.TestCase):
    def test_adb_is_opt_in_and_identity_is_unset_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))

            self.assertFalse(settings.adb.enabled)
            self.assertIsNone(settings.adb.target_serial)
            self.assertIsNone(settings.adb.expected_fingerprint)
            self.assertEqual(settings.adb.expected_model, "SM-G975F")
            self.assertEqual(settings.screen.max_clients, 2)

    def test_unsafe_target_and_non_printable_fingerprint_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = load_settings(root)
            raw = json.loads(settings.config_path.read_text(encoding="utf-8"))
            raw["adb"]["enabled"] = True
            raw["adb"]["target_serial"] = "device;command"
            settings.config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_settings(root)

            raw["adb"]["target_serial"] = "192.0.2.10:37123"
            raw["adb"]["expected_fingerprint"] = "bad\u0000fingerprint"
            settings.config_path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_settings(root)
