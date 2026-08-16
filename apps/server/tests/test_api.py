import asyncio
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from s10_control.adb import AdbState, MockAdbController
from s10_control.auth import SESSION_COOKIE
from s10_control.config import load_settings
from s10_control.main import create_app
from s10_control.screen import PNG_SIGNATURE, Frame, FrameMetadata, MockScreenProvider, ScreenError, ScreenProvider


class WaitingMockAdbController(MockAdbController):
    """Pauses immediately before the mock's final typed-input precondition."""

    def __init__(self):
        super().__init__(rotation=0)
        self.execute_started = asyncio.Event()
        self.release_execute = asyncio.Event()

    async def execute(self, command, **kwargs) -> None:
        self.execute_started.set()
        await self.release_execute.wait()
        await super().execute(command, **kwargs)


class HangingScreenProvider(ScreenProvider):
    """Never produces a frame until test cleanup releases it."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    async def capture(self, stream_id: str) -> Frame:
        del stream_id
        self.started.set()
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        raise ScreenError("TEST_PROVIDER_RELEASED")


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_stays_ready_without_internet_or_adb(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            adb = MockAdbController(AdbState.UNAVAILABLE, reason="ADB_BINARY_MISSING")
            screen = MockScreenProvider(error_code="ADB_BINARY_MISSING")
            app = create_app(settings, adb_controller=adb, screen_provider=screen)
            with (
                patch("s10_control.metrics._port_open", new=AsyncMock(return_value=False)),
                patch(
                    "s10_control.metrics._battery_sample",
                    new=AsyncMock(return_value={"state": "unavailable", "reason": "TEST_PROVIDER_MISSING"}),
                ),
            ):
                async with app.router.lifespan_context(app):
                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                        self.assertEqual((await client.get("/api/v1/health/live")).json()["state"], "live")
                        ready = await client.get("/api/v1/health/ready")
                        self.assertEqual(ready.status_code, 200)
                        self.assertFalse(ready.json()["internet_required"])
                        self.assertFalse(ready.json()["adb_required"])
                        self.assertEqual(ready.headers["Cache-Control"], "no-store")
                        self.assertEqual(ready.headers["X-Frame-Options"], "DENY")
                        malformed_host = await client.get(
                            "/api/v1/health/ready",
                            headers={"Host": "attacker.invalid/api/v1/status"},
                        )
                        self.assertEqual(malformed_host.status_code, 200)
                        self.assertEqual(malformed_host.headers["Cache-Control"], "no-store")
                        self.assertFalse(malformed_host.json()["internet_required"])
                        self.assertEqual((await client.get("/api/v1/status")).status_code, 401)
                        token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                        exchanged = await client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                        self.assertEqual(exchanged.status_code, 200)
                        self.assertEqual(exchanged.json()["role"], "admin")
                        self.assertEqual((await client.get("/api/v1/auth/session")).status_code, 200)
                        status = await client.get("/api/v1/status")
                        self.assertEqual(status.status_code, 200)
                        self.assertEqual(status.json()["network"]["adb"]["state"], "unavailable")
                        self.assertEqual(status.json()["network"]["internet"]["state"], "offline")
                        self.assertEqual((await client.get("/api/v1/health/ready")).status_code, 200)
            self.assertEqual(adb.commands, [])

    async def test_shell_payload_and_unknown_fields_are_rejected_before_mock_adb(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            adb = MockAdbController()
            app = create_app(settings, adb_controller=adb, screen_provider=MockScreenProvider(error_code="NO_STREAM"))
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                    exchanged = await client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                    csrf = exchanged.json()["csrf_token"]
                    headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf}
                    frame = {
                        "stream_id": "stream-1",
                        "frame_id": "frame-1",
                        "display_id": 0,
                        "rotation": 0,
                        "adb_target": adb.target,
                        "adb_generation": adb.generation,
                    }

                    extra_field = await client.post(
                        "/api/v1/android/tap",
                        headers=headers,
                        json={**frame, "x": 0.5, "y": 0.5, "shell": "not-allowed"},
                    )
                    shell_action = await client.post(
                        "/api/v1/android/key",
                        headers=headers,
                        json={**frame, "action": "shell"},
                    )
                    shell_route = await client.post(
                        "/api/v1/android/shell",
                        headers=headers,
                        json={"command": "not-allowed"},
                    )
                    boolean_coordinate = await client.post(
                        "/api/v1/android/tap",
                        headers=headers,
                        json={**frame, "x": True, "y": 0.5},
                    )
                    coerced_duration = await client.post(
                        "/api/v1/android/swipe",
                        headers=headers,
                        json={
                            **frame,
                            "start_x": 0.1,
                            "start_y": 0.1,
                            "end_x": 0.9,
                            "end_y": 0.9,
                            "duration_ms": "500",
                        },
                    )
                    boolean_display = await client.post(
                        "/api/v1/android/tap",
                        headers=headers,
                        json={**frame, "display_id": False, "x": 0.5, "y": 0.5},
                    )

                    self.assertEqual(extra_field.status_code, 422)
                    self.assertEqual(shell_action.status_code, 422)
                    self.assertIn(shell_route.status_code, {404, 405})
                    self.assertEqual(boolean_coordinate.status_code, 422)
                    self.assertEqual(coerced_duration.status_code, 422)
                    self.assertEqual(boolean_display.status_code, 422)
                    self.assertEqual(adb.commands, [])

    async def test_confirmed_frame_and_csrf_are_required_for_typed_control(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            adb = MockAdbController(rotation=0)
            app = create_app(settings, adb_controller=adb, screen_provider=MockScreenProvider(error_code="NO_STREAM"))
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                    exchanged = await client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                    csrf = exchanged.json()["csrf_token"]
                    metadata = FrameMetadata(
                        stream_id="stream-1",
                        frame_id="frame-1",
                        width=101,
                        height=201,
                        rotation=0,
                        display_id=0,
                        mime="image/png",
                        observed_at="2026-08-15T00:00:00+00:00",
                        observed_monotonic=time.monotonic(),
                        adb_target=adb.target,
                        adb_generation=adb.generation,
                    )
                    session_cookie = client.cookies.get(SESSION_COOKIE)
                    self.assertIsNotNone(session_cookie)
                    owner_id = session_cookie.split(".", 1)[0]
                    app.state.frame_registry.confirm(owner_id, metadata)
                    payload = {
                        "stream_id": "stream-1",
                        "frame_id": "frame-1",
                        "display_id": 0,
                        "rotation": 0,
                        "adb_target": adb.target,
                        "adb_generation": adb.generation,
                        "x": 0.5,
                        "y": 0.5,
                    }

                    no_csrf = await client.post("/api/v1/android/tap", json=payload, headers={"Origin": "http://testserver"})
                    accepted = await client.post(
                        "/api/v1/android/tap",
                        json=payload,
                        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
                    )

                    self.assertEqual(no_csrf.status_code, 403)
                    self.assertEqual(accepted.status_code, 200)
                    self.assertEqual(accepted.json()["state"], "unverified")
                    self.assertEqual(len(adb.commands), 1)

    async def test_session_and_role_are_revalidated_while_input_waits_for_adb(self):
        scenarios = (
            ("revoked", 401),
            ("expired", 401),
            ("role_removed", 403),
        )
        for transition, expected_status in scenarios:
            with self.subTest(transition=transition), tempfile.TemporaryDirectory() as directory:
                settings = load_settings(Path(directory))
                adb = WaitingMockAdbController()
                app = create_app(
                    settings,
                    adb_controller=adb,
                    screen_provider=MockScreenProvider(error_code="NO_STREAM"),
                )
                async with app.router.lifespan_context(app):
                    transport = httpx.ASGITransport(app=app)
                    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                        token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                        exchanged = await client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                        csrf = exchanged.json()["csrf_token"]
                        session_cookie = client.cookies.get(SESSION_COOKIE)
                        self.assertIsNotNone(session_cookie)
                        owner_id = session_cookie.split(".", 1)[0]
                        metadata = FrameMetadata(
                            stream_id="stream-auth-race",
                            frame_id="frame-auth-race",
                            width=100,
                            height=200,
                            rotation=0,
                            display_id=0,
                            mime="image/png",
                            observed_at="2026-08-15T00:00:00+00:00",
                            observed_monotonic=time.monotonic(),
                            adb_target=adb.target,
                            adb_generation=adb.generation,
                        )
                        app.state.frame_registry.confirm(owner_id, metadata)
                        payload = {
                            "stream_id": metadata.stream_id,
                            "frame_id": metadata.frame_id,
                            "display_id": metadata.display_id,
                            "rotation": metadata.rotation,
                            "adb_target": metadata.adb_target,
                            "adb_generation": metadata.adb_generation,
                            "x": 0.5,
                            "y": 0.5,
                        }
                        operation = asyncio.create_task(client.post(
                            "/api/v1/android/tap",
                            json=payload,
                            headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
                        ))
                        try:
                            await asyncio.wait_for(adb.execute_started.wait(), timeout=1.0)
                            if transition == "revoked":
                                app.state.auth.revoke(session_cookie)
                            elif transition == "expired":
                                with app.state.database:
                                    app.state.database.execute(
                                        "UPDATE sessions SET expires_at = 0 WHERE id = ?",
                                        (owner_id,),
                                    )
                            else:
                                with app.state.database:
                                    app.state.database.execute(
                                        "UPDATE sessions SET role = 'viewer' WHERE id = ?",
                                        (owner_id,),
                                    )
                        finally:
                            adb.release_execute.set()

                        response = await asyncio.wait_for(operation, timeout=1.0)
                        self.assertEqual(adb.commands, [])
                        self.assertEqual(response.status_code, expected_status)


class WebSocketApiTests(unittest.TestCase):
    def test_authenticated_png_frame_requires_exact_ack_before_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            metadata = FrameMetadata(
                stream_id="fixture-stream",
                frame_id="fixture-frame",
                width=10,
                height=20,
                rotation=0,
                display_id=0,
                mime="image/png",
                observed_at="2026-08-15T00:00:00+00:00",
                observed_monotonic=time.monotonic(),
                adb_target="mock-device",
                adb_generation=1,
            )
            png = PNG_SIGNATURE + b"fixture-png"
            app = create_app(
                settings,
                adb_controller=MockAdbController(rotation=0),
                screen_provider=MockScreenProvider(frames=[Frame(metadata, png)]),
            )

            with TestClient(app, base_url="http://testserver") as client:
                token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                self.assertEqual(
                    client.post("/api/v1/auth/bootstrap/exchange", json={"token": token}).status_code,
                    200,
                )
                session_cookie = client.cookies.get(SESSION_COOKIE)
                self.assertIsNotNone(session_cookie)
                owner_id = session_cookie.split(".", 1)[0]
                with client.websocket_connect(
                    "/api/v1/screen/ws",
                    headers={"Origin": "http://testserver"},
                ) as socket:
                    stream_status = socket.receive_json()
                    frame_metadata = socket.receive_json()
                    frame_bytes = socket.receive_bytes()
                    self.assertEqual(stream_status["type"], "stream_status")
                    self.assertEqual(stream_status["frame_max_age_seconds"], settings.screen.frame_max_age_seconds)
                    self.assertIsNone(app.state.frame_registry.current_for(owner_id))
                    self.assertEqual(frame_bytes, png)
                    socket.send_json({
                        "type": "frame_ack",
                        "stream_id": frame_metadata["stream_id"],
                        "frame_id": frame_metadata["frame_id"],
                    })
                    socket.receive_json()
                    self.assertEqual(
                        app.state.frame_registry.current_for(owner_id).frame_id,
                        frame_metadata["frame_id"],
                    )

    def test_revoked_or_expired_session_cannot_ack_or_continue_existing_socket(self):
        for transition in ("revoked", "expired"):
            with self.subTest(transition=transition), tempfile.TemporaryDirectory() as directory:
                settings = load_settings(Path(directory))
                metadata = FrameMetadata(
                    stream_id="fixture-stream",
                    frame_id=f"fixture-{transition}",
                    width=10,
                    height=20,
                    rotation=0,
                    display_id=0,
                    mime="image/png",
                    observed_at="2026-08-15T00:00:00+00:00",
                    observed_monotonic=time.monotonic(),
                    adb_target="mock-device",
                    adb_generation=1,
                )
                app = create_app(
                    settings,
                    adb_controller=MockAdbController(rotation=0),
                    screen_provider=MockScreenProvider(frames=[Frame(metadata, PNG_SIGNATURE + b"fixture")]),
                )

                with TestClient(app, base_url="http://testserver") as client:
                    token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                    self.assertEqual(
                        client.post("/api/v1/auth/bootstrap/exchange", json={"token": token}).status_code,
                        200,
                    )
                    session_cookie = client.cookies.get(SESSION_COOKIE)
                    self.assertIsNotNone(session_cookie)
                    owner_id = session_cookie.split(".", 1)[0]

                    with client.websocket_connect(
                        "/api/v1/screen/ws",
                        headers={"Origin": "http://testserver"},
                    ) as socket:
                        socket.receive_json()
                        frame_metadata = socket.receive_json()
                        socket.receive_bytes()

                        if transition == "revoked":
                            app.state.auth.revoke(session_cookie)
                        else:
                            with app.state.database:
                                app.state.database.execute(
                                    "UPDATE sessions SET expires_at = 0 WHERE id = ?",
                                    (owner_id,),
                                )

                        socket.send_json({
                            "type": "frame_ack",
                            "stream_id": frame_metadata["stream_id"],
                            "frame_id": frame_metadata["frame_id"],
                        })
                        with self.assertRaises(WebSocketDisconnect) as context:
                            socket.receive_json()
                        self.assertEqual(context.exception.code, 4401)
                        self.assertIsNone(app.state.frame_registry.current_for(owner_id))

    def test_two_websockets_from_same_session_keep_control_frames_isolated_by_stream(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            adb = MockAdbController(rotation=0)
            metadata = FrameMetadata(
                stream_id="fixture-stream",
                frame_id="shared-provider-frame",
                width=100,
                height=200,
                rotation=0,
                display_id=0,
                mime="image/png",
                observed_at="2026-08-15T00:00:00+00:00",
                observed_monotonic=time.monotonic(),
                adb_target=adb.target,
                adb_generation=adb.generation,
            )
            app = create_app(
                settings,
                adb_controller=adb,
                screen_provider=MockScreenProvider(frames=[Frame(metadata, PNG_SIGNATURE + b"fixture")]),
            )

            with TestClient(app, base_url="http://testserver") as client:
                token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                exchanged = client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                csrf = exchanged.json()["csrf_token"]
                headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf}
                with (
                    client.websocket_connect("/api/v1/screen/ws", headers={"Origin": "http://testserver"}) as first,
                    client.websocket_connect("/api/v1/screen/ws", headers={"Origin": "http://testserver"}) as second,
                ):
                    first.receive_json()
                    first_frame = first.receive_json()
                    first.receive_bytes()
                    second.receive_json()
                    second_frame = second.receive_json()
                    second.receive_bytes()
                    self.assertNotEqual(first_frame["stream_id"], second_frame["stream_id"])

                    for socket, received in ((first, first_frame), (second, second_frame)):
                        socket.send_json({
                            "type": "frame_ack",
                            "stream_id": received["stream_id"],
                            "frame_id": received["frame_id"],
                        })
                        acknowledged = socket.receive_json()
                        self.assertEqual(acknowledged["type"], "frame_acknowledged")
                        self.assertEqual(acknowledged["stream_id"], received["stream_id"])
                        self.assertEqual(acknowledged["frame_id"], received["frame_id"])

                    def tap_payload(received: dict[str, object]) -> dict[str, object]:
                        return {
                            "stream_id": received["stream_id"],
                            "frame_id": received["frame_id"],
                            "display_id": received["display_id"],
                            "rotation": received["rotation"],
                            "adb_target": received["adb_target"],
                            "adb_generation": received["adb_generation"],
                            "x": 0.5,
                            "y": 0.5,
                        }

                    first_control = client.post("/api/v1/android/tap", headers=headers, json=tap_payload(first_frame))
                    second_control = client.post("/api/v1/android/tap", headers=headers, json=tap_payload(second_frame))
                    self.assertEqual(first_control.status_code, 200)
                    self.assertEqual(second_control.status_code, 200)
                    self.assertEqual(len(adb.commands), 2)

    def test_frame_acknowledged_is_emitted_only_after_registry_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            metadata = FrameMetadata(
                stream_id="fixture-stream",
                frame_id="frame-commit-order",
                width=10,
                height=20,
                rotation=0,
                display_id=0,
                mime="image/png",
                observed_at="2026-08-15T00:00:00+00:00",
                observed_monotonic=time.monotonic(),
                adb_target="mock-device",
                adb_generation=1,
            )
            app = create_app(
                settings,
                adb_controller=MockAdbController(rotation=0),
                screen_provider=MockScreenProvider(frames=[Frame(metadata, PNG_SIGNATURE + b"fixture")]),
            )

            with TestClient(app, base_url="http://testserver") as client:
                token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                registry = app.state.frame_registry
                original_confirm = registry.confirm
                commit_started = threading.Event()
                release_commit = threading.Event()
                commit_finished = threading.Event()

                def blocking_confirm(*args, **kwargs):
                    commit_started.set()
                    release_commit.wait(timeout=2.0)
                    result = original_confirm(*args, **kwargs)
                    commit_finished.set()
                    return result

                registry.confirm = blocking_confirm
                try:
                    with client.websocket_connect(
                        "/api/v1/screen/ws",
                        headers={"Origin": "http://testserver"},
                    ) as socket:
                        socket.receive_json()
                        received = socket.receive_json()
                        socket.receive_bytes()
                        socket.send_json({
                            "type": "frame_ack",
                            "stream_id": received["stream_id"],
                            "frame_id": received["frame_id"],
                        })
                        with ThreadPoolExecutor(max_workers=1) as pool:
                            acknowledgement = pool.submit(socket.receive_json)
                            self.assertTrue(commit_started.wait(timeout=1.0))
                            try:
                                time.sleep(0.05)
                                self.assertFalse(acknowledgement.done())
                            finally:
                                release_commit.set()
                            message = acknowledgement.result(timeout=2.0)

                        self.assertTrue(commit_finished.is_set())
                        self.assertEqual(message["type"], "frame_acknowledged")
                        self.assertEqual(message["stream_id"], received["stream_id"])
                        self.assertEqual(message["frame_id"], received["frame_id"])
                finally:
                    release_commit.set()
                    registry.confirm = original_confirm

    def test_websocket_revalidates_revoked_session_while_provider_is_stuck(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
            provider = HangingScreenProvider()
            app = create_app(
                settings,
                adb_controller=MockAdbController(rotation=0),
                screen_provider=provider,
            )

            with TestClient(app, base_url="http://testserver") as client:
                token = settings.bootstrap_path.read_text(encoding="utf-8").strip()
                client.post("/api/v1/auth/bootstrap/exchange", json={"token": token})
                session_cookie = client.cookies.get(SESSION_COOKIE)
                self.assertIsNotNone(session_cookie)
                with client.websocket_connect(
                    "/api/v1/screen/ws",
                    headers={"Origin": "http://testserver"},
                ) as socket:
                    self.assertEqual(socket.receive_json()["type"], "stream_status")
                    self.assertTrue(provider.started.wait(timeout=1.0))
                    app.state.auth.revoke(session_cookie)
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        closed = pool.submit(socket.receive_json)
                        try:
                            with self.assertRaises(WebSocketDisconnect) as context:
                                closed.result(timeout=2.0)
                            self.assertEqual(context.exception.code, 4401)
                        finally:
                            provider.release.set()
