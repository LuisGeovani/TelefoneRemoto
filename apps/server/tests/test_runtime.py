import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
from unittest.mock import patch

from s10_control.cli import GRACEFUL_SHUTDOWN_SECONDS, main
from s10_control.config import load_settings


SERVER_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SERVER_ROOT.parents[1]
RUNTIME_SMOKE = PROJECT_ROOT / "scripts" / "smoke-python-runtime.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_ready(port: int, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/v1/health/ready"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.25) as response:
                if response.status == 200 and json.load(response)["state"] == "ready":
                    return
        except Exception:
            time.sleep(0.05)
    raise AssertionError("server did not become ready")


def _open_authenticated_websocket(port: int, bootstrap_path: Path) -> socket.socket:
    token = bootstrap_path.read_text(encoding="utf-8").strip()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/auth/bootstrap/exchange",
        data=json.dumps({"token": token}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2.0) as response:
        cookie = SimpleCookie()
        cookie.load(response.headers["Set-Cookie"])
        session = cookie["s10_session"].value

    connection = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    connection.sendall(
        (
            "GET /api/v1/screen/ws HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            f"Origin: http://127.0.0.1:{port}\r\n"
            f"Cookie: s10_session={session}\r\n\r\n"
        ).encode("ascii")
    )
    response = connection.recv(4096)
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        connection.close()
        raise AssertionError(f"websocket handshake failed: {response[:200]!r}")
    return connection


class RuntimeCompatibilityTests(unittest.TestCase):
    def test_project_import_smoke_runs_in_a_fresh_interpreter(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["S10_CONTROL_DATA_DIR"] = directory
            result = subprocess.run(
                [sys.executable, str(RUNTIME_SMOKE)],
                cwd=SERVER_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10.0,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["state"], "ready")
        self.assertEqual(report["fastapi"], "0.118.3")
        self.assertEqual(report["pydantic"], "1.10.26")
        self.assertEqual(report["starlette"], "0.48.0")

    @patch("s10_control.cli.uvicorn.run")
    def test_cli_sets_a_bounded_graceful_shutdown(self, run):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"S10_CONTROL_DATA_DIR": directory}):
                self.assertEqual(main(["serve"]), 0)
        self.assertEqual(run.call_args.kwargs["timeout_graceful_shutdown"], GRACEFUL_SHUTDOWN_SECONDS)


@unittest.skipUnless(os.name == "posix", "SIGTERM lifecycle regression requires POSIX/Termux")
class SigtermLifecycleTests(unittest.TestCase):
    def test_real_uvicorn_exits_with_an_active_websocket_after_sigterm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = load_settings(root)
            raw = json.loads(settings.config_path.read_text(encoding="utf-8"))
            port = _free_port()
            raw["listen"] = {"host": "127.0.0.1", "port": port}
            settings.config_path.write_text(json.dumps(raw), encoding="utf-8")
            environment = os.environ.copy()
            environment["S10_CONTROL_DATA_DIR"] = directory
            process = subprocess.Popen(
                [sys.executable, "-m", "s10_control", "serve"],
                cwd=SERVER_ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            websocket = None
            try:
                _wait_ready(port)
                websocket = _open_authenticated_websocket(port, root / "bootstrap.token")
                started = time.monotonic()
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=GRACEFUL_SHUTDOWN_SECONDS + 4)
                elapsed = time.monotonic() - started
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertLess(elapsed, GRACEFUL_SHUTDOWN_SECONDS + 4)
            finally:
                if websocket is not None:
                    websocket.close()
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=2.0)
