import asyncio
import math
import time
import unittest
from dataclasses import replace

from s10_control.adb import AdbState, KeyCommand, MockAdbController, TapCommand, TextCommand
from s10_control.android_control import (
    AndroidControlService,
    ControlError,
    FrameReference,
    map_normalized_point,
)
from s10_control.screen import FrameMetadata, FrameRegistry

OWNER_ID = "session-a"


def frame_metadata(
    *,
    stream_id: str = "stream-1",
    frame_id: str = "frame-1",
    width: int = 100,
    height: int = 200,
    rotation: int | None = 0,
    age_seconds: float = 0.0,
    adb_target: str = "mock-device",
    adb_generation: int = 1,
) -> FrameMetadata:
    return FrameMetadata(
        stream_id=stream_id,
        frame_id=frame_id,
        width=width,
        height=height,
        rotation=rotation,
        display_id=0,
        mime="image/png",
        observed_at="2026-08-15T00:00:00+00:00",
        observed_monotonic=time.monotonic() - age_seconds,
        adb_target=adb_target,
        adb_generation=adb_generation,
    )


def reference_for(frame: FrameMetadata, *, rotation: int | None = None, frame_id: str | None = None) -> FrameReference:
    selected_rotation = frame.rotation if rotation is None else rotation
    if selected_rotation is None:
        selected_rotation = 0
    return FrameReference(
        stream_id=frame.stream_id,
        frame_id=frame_id or frame.frame_id,
        display_id=frame.display_id,
        rotation=selected_rotation,
        adb_target=frame.adb_target,
        adb_generation=frame.adb_generation,
    )


class CoordinateConversionTests(unittest.TestCase):
    def test_normalized_edges_and_center_map_to_real_frame_pixels(self):
        self.assertEqual(map_normalized_point(0.0, 0.0, 100, 200), (0, 0))
        self.assertEqual(map_normalized_point(1.0, 1.0, 100, 200), (99, 199))
        self.assertEqual(map_normalized_point(0.5, 0.5, 100, 200), (50, 100))

    def test_invalid_coordinates_and_dimensions_are_rejected(self):
        invalid_points = [(-0.01, 0.5), (1.01, 0.5), (0.5, -0.01), (0.5, 1.01), (math.nan, 0.5), (True, 0.5)]
        for x, y in invalid_points:
            with self.subTest(x=x, y=y), self.assertRaises(ControlError) as context:
                map_normalized_point(x, y, 100, 200)
            self.assertEqual(context.exception.code, "INVALID_COORDINATES")
        with self.assertRaises(ControlError) as context:
            map_normalized_point(0.5, 0.5, 0, 200)
        self.assertEqual(context.exception.code, "INVALID_FRAME")


class FrameBoundControlTests(unittest.IsolatedAsyncioTestCase):
    def service_for(self, frame: FrameMetadata, *, adb_rotation: int | None = None, max_age: float = 5.0):
        registry = FrameRegistry()
        registry.confirm(OWNER_ID, frame)
        adb = MockAdbController(
            state=AdbState.AVAILABLE,
            rotation=frame.rotation if adb_rotation is None else adb_rotation,
            target=frame.adb_target,
            generation=frame.adb_generation,
        )
        return AndroidControlService(adb, registry, max_age), adb

    async def test_all_supported_rotations_are_validated_without_hardcoded_resolution(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                frame = frame_metadata(width=73, height=131, rotation=rotation)
                service, adb = self.service_for(frame, adb_rotation=rotation)

                await service.tap(OWNER_ID, reference_for(frame), 1.0, 1.0)

                self.assertEqual(adb.commands, [TapCommand(72, 130)])

    async def test_rotation_change_and_reference_mismatch_are_rejected_as_stale(self):
        frame = frame_metadata(rotation=90)
        changed_service, changed_adb = self.service_for(frame, adb_rotation=180)
        with self.assertRaises(ControlError) as context:
            await changed_service.tap(OWNER_ID, reference_for(frame), 0.5, 0.5)
        self.assertEqual(context.exception.code, "STALE_FRAME")
        self.assertEqual(changed_adb.commands, [])

        service, adb = self.service_for(frame, adb_rotation=90)
        with self.assertRaises(ControlError) as context:
            await service.tap(OWNER_ID, reference_for(frame, rotation=0), 0.5, 0.5)
        self.assertEqual(context.exception.code, "ROTATION_MISMATCH")
        self.assertEqual(adb.commands, [])

    async def test_old_or_unknown_frame_cannot_control_android(self):
        stale = frame_metadata(age_seconds=30.0)
        stale_service, stale_adb = self.service_for(stale, max_age=1.0)
        with self.assertRaises(ControlError) as context:
            await stale_service.tap(OWNER_ID, reference_for(stale), 0.5, 0.5)
        self.assertEqual(context.exception.code, "STALE_FRAME")
        self.assertEqual(stale_adb.commands, [])

        unknown = frame_metadata(rotation=None)
        unknown_service, unknown_adb = self.service_for(unknown, adb_rotation=None)
        with self.assertRaises(ControlError) as context:
            await unknown_service.tap(OWNER_ID, reference_for(unknown), 0.5, 0.5)
        self.assertEqual(context.exception.code, "ROTATION_UNKNOWN")
        self.assertEqual(unknown_adb.commands, [])

    async def test_wrong_frame_id_is_rejected_before_an_adb_call(self):
        frame = frame_metadata()
        service, adb = self.service_for(frame)

        with self.assertRaises(ControlError) as context:
            await service.tap(OWNER_ID, reference_for(frame, frame_id="older-frame"), 0.5, 0.5)

        self.assertEqual(context.exception.code, "STALE_FRAME")
        self.assertEqual(adb.commands, [])

    async def test_frame_change_while_waiting_for_adb_blocks_execution(self):
        class BlockingRotationAdb(MockAdbController):
            def __init__(self):
                super().__init__(rotation=0)
                self.rotation_started = asyncio.Event()
                self.release_rotation = asyncio.Event()

            async def execute(
                self,
                command,
                *,
                expected_target: str,
                expected_generation: int,
                expected_rotation: int,
                precondition,
            ) -> None:
                self.rotation_started.set()
                await self.release_rotation.wait()
                precondition()
                await super().execute(
                    command,
                    expected_target=expected_target,
                    expected_generation=expected_generation,
                    expected_rotation=expected_rotation,
                    precondition=precondition,
                )

        initial = frame_metadata(frame_id="frame-before-wait")
        replacement = replace(
            frame_metadata(frame_id="frame-after-wait"),
            observed_monotonic=initial.observed_monotonic + 0.001,
        )
        registry = FrameRegistry()
        registry.confirm(OWNER_ID, initial)
        adb = BlockingRotationAdb()
        service = AndroidControlService(adb, registry, frame_max_age_seconds=5.0)

        operation = asyncio.create_task(service.tap(OWNER_ID, reference_for(initial), 0.5, 0.5))
        await asyncio.wait_for(adb.rotation_started.wait(), timeout=1.0)
        registry.confirm(OWNER_ID, replacement)
        adb.release_rotation.set()

        with self.assertRaises(ControlError) as context:
            await operation
        self.assertEqual(context.exception.code, "STALE_FRAME")
        self.assertEqual(adb.commands, [])

    async def test_frame_expiry_while_waiting_for_adb_blocks_execution(self):
        class BlockingRotationAdb(MockAdbController):
            def __init__(self):
                super().__init__(rotation=0)
                self.rotation_started = asyncio.Event()
                self.release_rotation = asyncio.Event()

            async def execute(
                self,
                command,
                *,
                expected_target: str,
                expected_generation: int,
                expected_rotation: int,
                precondition,
            ) -> None:
                self.rotation_started.set()
                await self.release_rotation.wait()
                precondition()
                await super().execute(
                    command,
                    expected_target=expected_target,
                    expected_generation=expected_generation,
                    expected_rotation=expected_rotation,
                    precondition=precondition,
                )

        current = frame_metadata()
        registry = FrameRegistry()
        registry.confirm(OWNER_ID, current)
        adb = BlockingRotationAdb()
        service = AndroidControlService(adb, registry, frame_max_age_seconds=0.01)

        operation = asyncio.create_task(service.tap(OWNER_ID, reference_for(current), 0.5, 0.5))
        await asyncio.wait_for(adb.rotation_started.wait(), timeout=1.0)
        await asyncio.sleep(0.02)
        adb.release_rotation.set()

        with self.assertRaises(ControlError) as context:
            await operation
        self.assertEqual(context.exception.code, "STALE_FRAME")
        self.assertEqual(adb.commands, [])

    async def test_only_the_session_that_acknowledged_a_frame_can_control_it(self):
        frame = frame_metadata()
        registry = FrameRegistry()
        registry.confirm("session-that-acked", frame)
        adb = MockAdbController(
            rotation=frame.rotation,
            target=frame.adb_target,
            generation=frame.adb_generation,
        )
        service = AndroidControlService(adb, registry, frame_max_age_seconds=5.0)

        with self.assertRaises(ControlError) as context:
            await service.tap("different-session", reference_for(frame), 0.5, 0.5)
        self.assertEqual(context.exception.code, "FRAME_REQUIRED")
        self.assertEqual(adb.commands, [])

        await service.tap("session-that-acked", reference_for(frame), 0.5, 0.5)
        self.assertEqual(adb.commands, [TapCommand(50, 100)])

    async def test_adb_generation_or_target_change_invalidates_confirmed_frame(self):
        scenarios = (
            {"target": "mock-device", "generation": 2},
            {"target": "different-device", "generation": 1},
        )
        for status in scenarios:
            with self.subTest(status=status):
                frame = frame_metadata(adb_target="mock-device", adb_generation=1)
                registry = FrameRegistry()
                registry.confirm(OWNER_ID, frame)
                adb = MockAdbController(rotation=0, **status)
                service = AndroidControlService(adb, registry, frame_max_age_seconds=5.0)

                with self.assertRaises(ControlError) as context:
                    await service.tap(OWNER_ID, reference_for(frame), 0.5, 0.5)

                self.assertEqual(context.exception.code, "STALE_FRAME")
                self.assertEqual(adb.commands, [])

    async def test_key_and_text_remain_typed_and_sleep_requires_confirmation(self):
        frame = frame_metadata()
        service, adb = self.service_for(frame)
        reference = reference_for(frame)

        await service.key(OWNER_ID, reference, "home")
        await service.text(OWNER_ID, reference, "safe text")
        with self.assertRaises(ControlError) as context:
            await service.key(OWNER_ID, reference, "sleep", confirmed=False)

        self.assertEqual(context.exception.code, "CONFIRMATION_REQUIRED")
        self.assertEqual(adb.commands, [KeyCommand("home"), TextCommand("safe text")])

    async def test_text_metacharacters_are_rejected_by_the_mock_validation_path(self):
        frame = frame_metadata()
        service, adb = self.service_for(frame)

        for text in ("unsafe;command", "unsafe|command", "unsafe&command", "unsafe$(command)", "unsafe`command`", "unsafe'quote", "unsafe(command)"):
            with self.subTest(text=text), self.assertRaises(ControlError) as context:
                await service.text(OWNER_ID, reference_for(frame), text)
            self.assertEqual(context.exception.code, "TEXT_NOT_ALLOWED")
        self.assertEqual(adb.commands, [])
