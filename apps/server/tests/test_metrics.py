import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from s10_control.config import load_settings
from s10_control.metrics import MetricsService, classify_addresses, parse_meminfo, parse_proc_stat, parse_uptime


class ParserTests(unittest.TestCase):
    def test_meminfo_converts_kib_to_bytes(self):
        self.assertEqual(parse_meminfo("MemTotal: 1024 kB\nMemAvailable: 512 kB\n"), {"MemTotal": 1048576, "MemAvailable": 524288})

    def test_proc_stat_and_uptime_are_tolerant(self):
        self.assertEqual(parse_proc_stat("cpu  1 2 3 4 5 6\n"), (21, 9))
        self.assertIsNone(parse_proc_stat("cpu malformed"))
        self.assertEqual(parse_uptime("12.50 7.0"), 12.5)
        self.assertIsNone(parse_uptime(""))

    def test_private_address_classification(self):
        self.assertEqual(classify_addresses(["127.0.0.1", "192.168.1.9", "8.8.8.8", "bad", "10.0.0.2"]), ["10.0.0.2", "192.168.1.9"])


class DegradationTests(unittest.IsolatedAsyncioTestCase):
    async def test_internet_offline_does_not_affect_local_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MetricsService(load_settings(Path(directory)))
            with patch("s10_control.metrics._port_open", side_effect=[False, False]):
                network = await service.network()
            self.assertEqual(network["internet"]["state"], "offline")
            self.assertIn("source", service.cpu())
            self.assertIn("total_bytes", service.storage())

    async def test_missing_adb_is_a_state_not_an_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MetricsService(load_settings(Path(directory)))
            with patch("s10_control.metrics.shutil.which", return_value=None), patch("s10_control.metrics._port_open", return_value=False):
                network = await service.network()
            self.assertEqual(network["adb"], {"state": "unavailable", "reason": "NOT_PROBED_IN_M1", "binary_present": False})
