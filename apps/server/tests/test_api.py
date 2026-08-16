import tempfile
import unittest
from pathlib import Path

import httpx

from s10_control.config import load_settings
from s10_control.main import create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_stays_ready_without_internet_or_adb(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            app = create_app(settings)
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    self.assertEqual((await client.get("/api/v1/health/live")).json()["state"], "live")
                    ready = await client.get("/api/v1/health/ready")
                    self.assertEqual(ready.status_code, 200)
                    self.assertFalse(ready.json()["internet_required"])
                    self.assertEqual((await client.get("/api/v1/status")).status_code, 401)
                    token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                    exchanged = await client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                    self.assertEqual(exchanged.status_code, 200)
                    self.assertEqual(exchanged.json()["role"], "admin")
                    self.assertEqual((await client.get("/api/v1/auth/session")).status_code, 200)
