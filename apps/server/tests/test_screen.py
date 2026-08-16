import asyncio
import struct
import time
import unittest

from s10_control.adb import MockAdbController, ProcessResult, SubprocessAdbController
from s10_control.config import AdbConfig
from s10_control.screen import (
    PNG_SIGNATURE,
    AdbScreenProvider,
    Frame,
    FrameMetadata,
    FrameRegistry,
    LatestFrameQueue,
    ScreenError,
    ScreenProvider,
    ScreenStreamHub,
    parse_png_dimensions,
)


def png_header(width: int, height: int) -> bytes:
    """Small parser fixture; production accepts dimensions from the IHDR header."""
    return PNG_SIGNATURE + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)


def frame(sequence: int, *, stream_id: str = "stream") -> Frame:
    metadata = FrameMetadata(
        stream_id=stream_id,
        frame_id=f"frame-{sequence}",
        width=100 + sequence,
        height=200 + sequence,
        rotation=0,
        display_id=0,
        mime="image/png",
        observed_at="2026-08-15T00:00:00+00:00",
        observed_monotonic=time.monotonic(),
        adb_target="mock-device",
        adb_generation=1,
    )
    return Frame(metadata, png_header(metadata.width, metadata.height))


class PngParserTests(unittest.TestCase):
    def test_png_dimensions_come_from_ihdr_without_a_fixed_s10_resolution(self):
        self.assertEqual(parse_png_dimensions(png_header(1441, 3039)), (1441, 3039))

    def test_invalid_png_signature_header_and_dimensions_are_rejected(self):
        fixtures = [
            b"not-a-png",
            PNG_SIGNATURE + struct.pack(">I", 12) + b"IHDR" + struct.pack(">II", 100, 200),
            png_header(0, 200),
            png_header(20000, 200),
        ]
        for fixture in fixtures:
            with self.subTest(fixture=fixture[:16]), self.assertRaises(ScreenError):
                parse_png_dimensions(fixture)


class ScreenProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_adb_screen_provider_uses_mock_controller_for_png_and_rotation(self):
        png = png_header(1080, 2280)
        adb = MockAdbController(png=png, rotation=90)
        provider = AdbScreenProvider(adb)

        captured = await provider.capture("stream-1")

        self.assertEqual((captured.metadata.width, captured.metadata.height), (1080, 2280))
        self.assertEqual(captured.metadata.rotation, 90)
        self.assertEqual(captured.metadata.stream_id, "stream-1")
        self.assertEqual(captured.metadata.mime, "image/png")
        self.assertEqual(captured.data, png)
        self.assertEqual(adb.capture_count, 1)

    async def test_provider_rejects_rotation_that_changes_during_capture(self):
        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        fingerprint = "samsung/beyond2lte/beyond2:12/example:user/release-keys"
        screenshot = png_header(1080, 2280)
        expected = [
            ((binary, "devices", "-l"), ProcessResult(0, f"List of devices attached\n{serial}\tdevice model:SM_G975F\n".encode(), b"")),
            ((binary, "mdns", "services"), ProcessResult(0, b"", b"")),
            ((binary, "-s", serial, "shell", "getprop", "ro.product.model"), ProcessResult(0, b"SM-G975F\n", b"")),
            ((binary, "-s", serial, "shell", "getprop", "ro.build.fingerprint"), ProcessResult(0, f"{fingerprint}\n".encode(), b"")),
            ((binary, "-s", serial, "shell", "dumpsys", "input"), ProcessResult(0, b"SurfaceOrientation: 0\n", b"")),
            ((binary, "-s", serial, "exec-out", "screencap", "-p"), ProcessResult(0, screenshot, b"")),
            ((binary, "-s", serial, "shell", "dumpsys", "input"), ProcessResult(0, b"SurfaceOrientation: 1\n", b"")),
        ]
        calls: list[tuple[str, ...]] = []

        async def fake_runner(arguments, timeout: float, output_limit: int) -> ProcessResult:
            del timeout, output_limit
            call = tuple(arguments)
            calls.append(call)
            if not expected:
                raise AssertionError(f"unexpected fake ADB invocation: {call!r}")
            expected_call, response = expected.pop(0)
            if call != expected_call:
                raise AssertionError(f"expected {expected_call!r}, got {call!r}")
            return response

        adb = SubprocessAdbController(
            AdbConfig(
                enabled=True,
                target_serial=serial,
                expected_fingerprint=fingerprint,
                expected_model="SM-G975F",
                status_cache_seconds=3.0,
                command_timeout_seconds=1.0,
                screenshot_timeout_seconds=2.0,
            ),
            runner=fake_runner,
            binary_resolver=lambda: binary,
        )
        await adb.status(force=True)
        provider = AdbScreenProvider(adb)

        with self.assertRaises(ScreenError) as context:
            await provider.capture("stream-rotation-change")

        self.assertEqual(context.exception.code, "ROTATION_CHANGED")
        self.assertFalse(expected)
        self.assertEqual(calls.count((binary, "-s", serial, "exec-out", "screencap", "-p")), 1)

    async def test_unknown_rotation_still_allows_read_only_screenshot(self):
        png = png_header(720, 1280)
        provider = AdbScreenProvider(MockAdbController(png=png, rotation=None))

        captured = await provider.capture("stream-read-only")

        self.assertIsNone(captured.metadata.rotation)
        self.assertEqual(captured.metadata.orientation, "portrait")

    async def test_latest_frame_queue_drops_old_items_instead_of_accumulating(self):
        queue = LatestFrameQueue()
        first, second, third = frame(1), frame(2), frame(3)

        queue.publish(first)
        queue.publish(second)
        queue.publish(third)

        self.assertEqual(queue.size, 1)
        self.assertEqual(queue.dropped, 2)
        self.assertIs(await queue.get(), third)


class CountingScreenProvider(ScreenProvider):
    def __init__(self, target_count: int):
        self.target_count = target_count
        self.capture_count = 0
        self.reached_target = asyncio.Event()

    async def capture(self, stream_id: str) -> Frame:
        self.capture_count += 1
        if self.capture_count >= self.target_count:
            self.reached_target.set()
        return frame(self.capture_count, stream_id=stream_id)


class StreamBackpressureTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_subscriber_keeps_only_latest_frame(self):
        provider = CountingScreenProvider(target_count=4)
        registry = FrameRegistry()
        hub = ScreenStreamHub(provider, fps=100.0, registry=registry)
        subscription = await hub.subscribe()
        try:
            await asyncio.wait_for(provider.reached_target.wait(), timeout=1.0)
            self.assertGreaterEqual(provider.capture_count, 4)
            self.assertEqual(subscription.queue.size, 1)
            self.assertGreaterEqual(subscription.queue.dropped, 3)
            latest = await subscription.queue.get()
            self.assertIsInstance(latest, Frame)
            self.assertEqual(latest.metadata.frame_id, f"frame-{provider.capture_count}")
        finally:
            await hub.unsubscribe(subscription)

    async def test_registry_contains_only_confirmed_current_frame_and_clears_by_stream(self):
        registry = FrameRegistry()
        current = frame(1, stream_id="stream-a").metadata

        registry.confirm("owner-a", current)
        registry.clear_stream("stream-b")
        self.assertIs(registry.current_for("owner-a"), current)
        registry.clear_stream("stream-a")
        self.assertIsNone(registry.current_for("owner-a"))

    async def test_late_ack_cannot_replace_a_newer_confirmed_frame(self):
        registry = FrameRegistry()
        older = frame(1).metadata
        await asyncio.sleep(0)
        newer = frame(2).metadata

        registry.confirm("owner-a", newer)
        registry.confirm("owner-a", older)

        self.assertIs(registry.current_for("owner-a"), newer)

    async def test_late_ack_after_provider_invalidation_cannot_restore_stale_frame(self):
        registry = FrameRegistry()
        sent_before_failure = frame(1, stream_id="stream-before-failure").metadata

        registry.clear_all()
        registry.confirm("owner-a", sent_before_failure)

        self.assertIsNone(registry.current_for("owner-a"))

    async def test_subscriber_capacity_is_bounded(self):
        provider = CountingScreenProvider(target_count=1)
        hub = ScreenStreamHub(provider, fps=1.0, registry=FrameRegistry(), max_clients=1)
        first = await hub.subscribe()
        try:
            with self.assertRaises(ScreenError) as context:
                await hub.subscribe()
            self.assertEqual(context.exception.code, "STREAM_CAPACITY")
        finally:
            await hub.unsubscribe(first)
