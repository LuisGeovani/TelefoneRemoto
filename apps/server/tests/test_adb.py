import asyncio
import sys
import time
import unittest

from s10_control.adb import (
    AdbError,
    AdbState,
    KeyCommand,
    MockAdbController,
    ProcessResult,
    SubprocessAdbController,
    TapCommand,
    parse_adb_devices,
    parse_mdns_services,
    parse_rotation,
    run_limited_process,
)
from s10_control.config import AdbConfig
from s10_control.android_control import AndroidControlService, ControlError, FrameReference
from s10_control.screen import FrameMetadata, FrameRegistry


def adb_config(
    *,
    target_serial: str | None = "192.0.2.10:37123",
    expected_fingerprint: str | None = "samsung/beyond2lte/beyond2:12/example:user/release-keys",
) -> AdbConfig:
    return AdbConfig(
        enabled=True,
        target_serial=target_serial,
        expected_fingerprint=expected_fingerprint,
        expected_model="SM-G975F",
        status_cache_seconds=3.0,
        command_timeout_seconds=1.0,
        screenshot_timeout_seconds=2.0,
    )


class FakeRunner:
    """Deterministic runner that never starts a host process."""

    def __init__(self, responses: list[tuple[tuple[str, ...], ProcessResult | BaseException]]):
        self.responses = list(responses)
        self.calls: list[tuple[tuple[str, ...], float, int]] = []

    async def __call__(self, arguments, timeout: float, output_limit: int) -> ProcessResult:
        call = tuple(arguments)
        self.calls.append((call, timeout, output_limit))
        if not self.responses:
            raise AssertionError(f"unexpected fake ADB invocation: {call!r}")
        expected, response = self.responses.pop(0)
        if call != expected:
            raise AssertionError(f"expected {expected!r}, got {call!r}")
        if isinstance(response, BaseException):
            raise response
        return response


def result(stdout: str = "", stderr: str = "", returncode: int = 0) -> ProcessResult:
    return ProcessResult(returncode, stdout.encode(), stderr.encode())


class AdbParserTests(unittest.TestCase):
    def test_devices_parser_preserves_runtime_states_and_transport(self):
        devices = parse_adb_devices(
            "* daemon started successfully\r\n"
            "List of devices attached\r\n"
            "USB123\tdevice product:beyond2lte model:SM_G975F transport_id:1\r\n"
            "192.0.2.10:37123\tunauthorized transport_id:2\r\n"
            "[fe80::10%wlan0]:37124\tdevice model:OTHER transport_id:4\r\n"
            "emulator-5554\toffline transport_id:3\r\n"
            "malformed\r\n"
        )

        self.assertEqual([item.state for item in devices], ["device", "unauthorized", "device", "offline"])
        self.assertEqual([item.transport for item in devices], ["usb", "tcp", "tcp", "emulator"])
        self.assertEqual(devices[0].details["model"], "SM_G975F")

    def test_mdns_and_rotation_parsers_are_tolerant(self):
        services = parse_mdns_services(
            "adb-one _adb-tls-connect._tcp 192.0.2.5:39801\n"
            "adb-six _adb-tls-connect._tcp [fe80::10%wlan0]:37199\n"
            "adb-pair _adb-tls-pairing._tcp 192.0.2.5:40001\n"
        )
        self.assertEqual(services, ["192.0.2.5:39801", "[fe80::10%wlan0]:37199"])
        self.assertEqual(parse_rotation("SurfaceOrientation: 0"), 0)
        self.assertEqual(parse_rotation("mCurrentRotation=ROTATION_1"), 90)
        self.assertEqual(parse_rotation("rotation=2"), 180)
        self.assertEqual(parse_rotation("rotation: 3"), 270)
        self.assertIsNone(parse_rotation("rotation unavailable"))


class AdbControllerStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_verified_target_becomes_available_using_only_fake_runner(self):
        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        fingerprint = "samsung/beyond2lte/beyond2:12/example:user/release-keys"
        runner = FakeRunner([
            ((binary, "devices", "-l"), result(f"List of devices attached\n{serial}\tdevice model:SM_G975F transport_id:1\n")),
            ((binary, "mdns", "services"), result()),
            ((binary, "-s", serial, "shell", "getprop", "ro.product.model"), result("SM-G975F\n")),
            ((binary, "-s", serial, "shell", "getprop", "ro.build.fingerprint"), result(f"{fingerprint}\n")),
        ])
        controller = SubprocessAdbController(adb_config(), runner=runner, binary_resolver=lambda: binary)

        self.assertEqual(controller.current_status.state, AdbState.CONNECTING)
        status = await controller.status(force=True)

        self.assertEqual(status.state, AdbState.AVAILABLE)
        self.assertEqual(status.reason, "IDENTITY_VERIFIED")
        self.assertEqual(status.target, serial)
        self.assertFalse(runner.responses)
        for call, _, _ in runner.calls[2:]:
            self.assertEqual(call[1:3], ("-s", serial))

    async def test_unavailable_unauthorized_and_error_states_do_not_run_real_adb(self):
        never_called = FakeRunner([])
        missing = SubprocessAdbController(adb_config(), runner=never_called, binary_resolver=lambda: None)
        self.assertEqual((await missing.status(force=True)).state, AdbState.UNAVAILABLE)
        self.assertEqual(missing.current_status.reason, "ADB_BINARY_MISSING")
        self.assertEqual(never_called.calls, [])

        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        unauthorized_runner = FakeRunner([
            ((binary, "devices", "-l"), result(f"List of devices attached\n{serial}\tunauthorized transport_id:1\n")),
            ((binary, "mdns", "services"), result()),
        ])
        unauthorized = SubprocessAdbController(adb_config(), runner=unauthorized_runner, binary_resolver=lambda: binary)
        self.assertEqual((await unauthorized.status(force=True)).state, AdbState.UNAUTHORIZED)
        self.assertEqual(unauthorized.current_status.reason, "AUTHORIZATION_REQUIRED")

        timeout_runner = FakeRunner([
            ((binary, "devices", "-l"), AdbError("TIMEOUT")),
        ])
        timeout = SubprocessAdbController(adb_config(), runner=timeout_runner, binary_resolver=lambda: binary)
        self.assertEqual((await timeout.status(force=True)).state, AdbState.ERROR)
        self.assertEqual(timeout.current_status.reason, "TIMEOUT")

    async def test_fingerprint_is_required_before_android_operations(self):
        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        runner = FakeRunner([
            ((binary, "devices", "-l"), result(f"List of devices attached\n{serial}\tdevice model:SM_G975F\n")),
            ((binary, "mdns", "services"), result()),
        ])
        controller = SubprocessAdbController(
            adb_config(expected_fingerprint=None),
            runner=runner,
            binary_resolver=lambda: binary,
        )

        status = await controller.status(force=True)

        self.assertEqual(status.state, AdbState.UNAVAILABLE)
        self.assertEqual(status.reason, "FINGERPRINT_REQUIRED")
        with self.assertRaisesRegex(AdbError, "ADB target is unavailable"):
            await controller.execute(
                TapCommand(1, 1),
                expected_target=serial,
                expected_generation=status.generation,
                expected_rotation=0,
                precondition=lambda: None,
            )
        self.assertFalse(runner.responses)

    async def test_changed_wireless_port_is_rediscovered_and_identity_checked(self):
        binary = "/fake/adb"
        old_serial = "127.0.0.1:5555"
        discovered = "192.0.2.10:39877"
        fingerprint = "samsung/beyond2lte/beyond2:12/example:user/release-keys"
        runner = FakeRunner([
            ((binary, "devices", "-l"), result(
                f"List of devices attached\n{old_serial}\toffline\n{discovered}\tdevice model:SM_G975F\n"
            )),
            ((binary, "mdns", "services"), result(f"s10 _adb-tls-connect._tcp {discovered}\n")),
            ((binary, "-s", discovered, "shell", "getprop", "ro.product.model"), result("SM-G975F\n")),
            ((binary, "-s", discovered, "shell", "getprop", "ro.build.fingerprint"), result(f"{fingerprint}\n")),
        ])
        controller = SubprocessAdbController(
            adb_config(target_serial=old_serial, expected_fingerprint=fingerprint),
            runner=runner,
            binary_resolver=lambda: binary,
        )

        status = await controller.status(force=True)

        self.assertEqual(status.state, AdbState.AVAILABLE)
        self.assertEqual(status.target, discovered)
        self.assertNotEqual(status.target, old_serial)

    async def test_model_and_fingerprint_mismatches_fail_closed(self):
        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        expected = "samsung/beyond2lte/beyond2:12/example:user/release-keys"
        cases = [
            ("OTHER", expected, "MODEL_MISMATCH"),
            ("SM-G975F", "samsung/other/device:12/example:user/release-keys", "FINGERPRINT_MISMATCH"),
        ]
        for model, observed_fingerprint, reason in cases:
            with self.subTest(reason=reason):
                runner = FakeRunner([
                    ((binary, "devices", "-l"), result(f"List of devices attached\n{serial}\tdevice model:SM_G975F\n")),
                    ((binary, "mdns", "services"), result()),
                    ((binary, "-s", serial, "shell", "getprop", "ro.product.model"), result(f"{model}\n")),
                    ((binary, "-s", serial, "shell", "getprop", "ro.build.fingerprint"), result(f"{observed_fingerprint}\n")),
                ])
                controller = SubprocessAdbController(
                    adb_config(expected_fingerprint=expected),
                    runner=runner,
                    binary_resolver=lambda: binary,
                )

                status = await controller.status(force=True)

                self.assertEqual(status.state, AdbState.ERROR)
                self.assertEqual(status.reason, reason)
                with self.assertRaises(AdbError):
                    await controller.execute(
                        TapCommand(1, 1),
                        expected_target=serial,
                        expected_generation=status.generation,
                        expected_rotation=0,
                        precondition=lambda: None,
                    )

    async def test_ambiguous_devices_are_not_selected(self):
        binary = "/fake/adb"
        runner = FakeRunner([
            ((binary, "devices", "-l"), result(
                "List of devices attached\n"
                "192.0.2.10:37123\tdevice model:SM_G975F\n"
                "192.0.2.11:37124\tdevice model:SM_G975F\n"
            )),
            ((binary, "mdns", "services"), result()),
        ])
        controller = SubprocessAdbController(
            adb_config(target_serial=None),
            runner=runner,
            binary_resolver=lambda: binary,
        )

        status = await controller.status(force=True)

        self.assertEqual(status.state, AdbState.UNAVAILABLE)
        self.assertEqual(status.reason, "NO_MATCHING_DEVICE")
        self.assertFalse(runner.responses)

    async def test_changed_transport_id_increments_generation_and_invalidates_old_frame(self):
        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        fingerprint = "samsung/beyond2lte/beyond2:12/example:user/release-keys"
        runner = FakeRunner([
            ((binary, "devices", "-l"), result(f"List of devices attached\n{serial}\tdevice model:SM_G975F transport_id:1\n")),
            ((binary, "mdns", "services"), result()),
            ((binary, "-s", serial, "shell", "getprop", "ro.product.model"), result("SM-G975F\n")),
            ((binary, "-s", serial, "shell", "getprop", "ro.build.fingerprint"), result(f"{fingerprint}\n")),
            ((binary, "devices", "-l"), result(f"List of devices attached\n{serial}\tdevice model:SM_G975F transport_id:2\n")),
            ((binary, "mdns", "services"), result()),
            ((binary, "-s", serial, "shell", "getprop", "ro.product.model"), result("SM-G975F\n")),
            ((binary, "-s", serial, "shell", "getprop", "ro.build.fingerprint"), result(f"{fingerprint}\n")),
        ])
        controller = SubprocessAdbController(
            adb_config(target_serial=serial, expected_fingerprint=fingerprint),
            runner=runner,
            binary_resolver=lambda: binary,
        )
        first = await controller.status(force=True)
        metadata = FrameMetadata(
            stream_id="stream-before-reconnect",
            frame_id="frame-before-reconnect",
            width=100,
            height=200,
            rotation=0,
            display_id=0,
            mime="image/png",
            observed_at="2026-08-15T00:00:00+00:00",
            observed_monotonic=time.monotonic(),
            adb_target=serial,
            adb_generation=first.generation,
        )
        registry = FrameRegistry()
        registry.confirm("owner-a", metadata)
        second = await controller.status(force=True)

        self.assertGreater(second.generation, first.generation)
        service = AndroidControlService(controller, registry, frame_max_age_seconds=5.0)
        reference = FrameReference(
            metadata.stream_id,
            metadata.frame_id,
            metadata.display_id,
            metadata.rotation,
            metadata.adb_target,
            metadata.adb_generation,
        )
        with self.assertRaises(ControlError) as context:
            await service.tap("owner-a", reference, 0.5, 0.5)
        self.assertEqual(context.exception.code, "STALE_FRAME")
        self.assertFalse(runner.responses)

    async def test_input_waiting_for_transport_is_not_starved_by_queued_captures(self):
        binary = "/fake/adb"
        serial = "192.0.2.10:37123"
        fingerprint = "samsung/beyond2lte/beyond2:12/example:user/release-keys"
        first_capture_started = asyncio.Event()
        release_first_capture = asyncio.Event()
        operations: list[str] = []
        capture_count = 0

        async def runner(arguments, timeout: float, output_limit: int) -> ProcessResult:
            nonlocal capture_count
            del timeout, output_limit
            call = tuple(arguments)
            if call == (binary, "devices", "-l"):
                return result(f"List of devices attached\n{serial}\tdevice model:SM_G975F transport_id:1\n")
            if call == (binary, "mdns", "services"):
                return result()
            if call == (binary, "-s", serial, "shell", "getprop", "ro.product.model"):
                return result("SM-G975F\n")
            if call == (binary, "-s", serial, "shell", "getprop", "ro.build.fingerprint"):
                return result(f"{fingerprint}\n")
            if call == (binary, "-s", serial, "shell", "dumpsys", "input"):
                return result("SurfaceOrientation: 0\n")
            if call == (binary, "-s", serial, "exec-out", "screencap", "-p"):
                capture_count += 1
                operations.append(f"capture-{capture_count}-started")
                if capture_count == 1:
                    first_capture_started.set()
                    await release_first_capture.wait()
                operations.append(f"capture-{capture_count}-finished")
                return ProcessResult(0, b"png", b"")
            if call == (binary, "-s", serial, "shell", "input", "tap", "1", "2"):
                operations.append("input")
                return result()
            raise AssertionError(f"unexpected fake ADB invocation: {call!r}")

        controller = SubprocessAdbController(
            adb_config(target_serial=serial, expected_fingerprint=fingerprint),
            runner=runner,
            binary_resolver=lambda: binary,
        )
        status = await controller.status(force=True)
        first_capture = asyncio.create_task(controller.capture_screen())
        queued_captures: list[asyncio.Task] = []
        input_task: asyncio.Task | None = None
        try:
            await asyncio.wait_for(first_capture_started.wait(), timeout=1.0)
            input_task = asyncio.create_task(controller.execute(
                TapCommand(1, 2),
                expected_target=serial,
                expected_generation=status.generation,
                expected_rotation=0,
                precondition=lambda: None,
            ))
            await asyncio.sleep(0)
            queued_captures = [asyncio.create_task(controller.capture_screen()) for _ in range(4)]
            release_first_capture.set()

            await asyncio.wait_for(input_task, timeout=1.0)
            await asyncio.wait_for(asyncio.gather(first_capture, *queued_captures), timeout=1.0)
        finally:
            release_first_capture.set()
            pending = [task for task in (first_capture, input_task, *queued_captures) if task is not None and not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        self.assertIn("input", operations)
        self.assertLess(operations.index("input"), operations.index("capture-2-started"))


class MockAdbControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_is_deterministic_and_records_only_typed_commands(self):
        mock = MockAdbController(png=b"png", rotation=270)

        self.assertEqual((await mock.status()).state, AdbState.AVAILABLE)
        capture = await mock.capture_screen()
        self.assertEqual(capture.png, b"png")
        self.assertEqual(capture.target, mock.target)
        self.assertEqual(capture.generation, mock.generation)
        self.assertEqual(await mock.display_rotation(), 270)
        await mock.execute(
            TapCommand(12, 34),
            expected_target=mock.target,
            expected_generation=mock.generation,
            expected_rotation=270,
            precondition=lambda: None,
        )

        self.assertEqual(mock.capture_count, 1)
        self.assertEqual(mock.commands, [TapCommand(12, 34)])
        with self.assertRaises(AdbError) as context:
            await mock.execute(
                KeyCommand("not_allowlisted"),
                expected_target=mock.target,
                expected_generation=mock.generation,
                expected_rotation=270,
                precondition=lambda: None,
            )
        self.assertEqual(context.exception.code, "COMMAND_NOT_ALLOWED")

    async def test_unavailable_mock_degrades_without_recording_a_command(self):
        mock = MockAdbController(AdbState.UNAVAILABLE, reason="ADB_BINARY_MISSING")

        with self.assertRaises(AdbError) as context:
            await mock.execute(
                TapCommand(1, 2),
                expected_target=mock.target,
                expected_generation=mock.generation,
                expected_rotation=0,
                precondition=lambda: None,
            )

        self.assertEqual(context.exception.code, "ADB_BINARY_MISSING")
        self.assertEqual(mock.commands, [])


class LimitedProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_stops_only_the_spawned_test_process(self):
        with self.assertRaises(AdbError) as context:
            await run_limited_process(
                (sys.executable, "-c", "import time; time.sleep(2)"),
                timeout=0.05,
                output_limit=1024,
            )
        self.assertEqual(context.exception.code, "TIMEOUT")

    async def test_output_limit_is_enforced(self):
        with self.assertRaises(AdbError) as context:
            await run_limited_process(
                (sys.executable, "-c", "import sys; sys.stdout.write('x' * 2048)"),
                timeout=1.0,
                output_limit=64,
            )
        self.assertEqual(context.exception.code, "OUTPUT_LIMIT")
