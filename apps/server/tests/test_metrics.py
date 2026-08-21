import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from s10_control.adb import AdbState, MockAdbController
from s10_control.config import load_settings
from s10_control.metrics import MetricsService, classify_addresses, discover_host_addresses, parse_meminfo, parse_proc_stat, parse_uptime


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

    @patch("s10_control.metrics._route_source_addresses", return_value=["192.168.1.20"])
    @patch("s10_control.metrics.socket.getaddrinfo", side_effect=OSError)
    def test_route_source_fallback_does_not_depend_on_hostname_or_iproute2(self, _getaddrinfo, _route):
        self.assertEqual(discover_host_addresses(), ["192.168.1.20"])

class DegradationTests(unittest.IsolatedAsyncioTestCase):
    async def test_observed_listener_address_keeps_lan_online_when_android_hostname_lookup_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MetricsService(load_settings(Path(directory)))
            service.observe_local_address(("192.168.1.20", 8080))
            with (
                patch("s10_control.metrics.socket.getaddrinfo", side_effect=OSError),
                patch("s10_control.metrics._route_source_addresses", return_value=[]),
                patch("s10_control.metrics._port_open", return_value=False),
            ):
                network = await service.network()
            self.assertEqual(network["lan"], {"state": "online", "addresses": ["192.168.1.20"], "reason": None})

    async def test_internet_offline_does_not_affect_local_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            service = MetricsService(
                load_settings(Path(directory)),
                MockAdbController(AdbState.UNAVAILABLE, reason="ADB_BINARY_MISSING"),
            )
            with patch("s10_control.metrics._port_open", side_effect=[False, False]):
                network = await service.network()
            self.assertEqual(network["internet"]["state"], "offline")
            self.assertIn("source", service.cpu())
            self.assertIn("total_bytes", service.storage())

    async def test_missing_adb_is_a_state_not_an_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            adb = MockAdbController(AdbState.UNAVAILABLE, reason="ADB_BINARY_MISSING")
            service = MetricsService(load_settings(Path(directory)), adb)
            with patch("s10_control.metrics._port_open", return_value=False):
                network = await service.network()
            self.assertEqual(network["adb"]["state"], "unavailable")
            self.assertEqual(network["adb"]["reason"], "ADB_BINARY_MISSING")
            self.assertEqual(adb.commands, [])
