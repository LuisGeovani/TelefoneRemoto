"""Frame-bound Android controls built from typed, allowlisted ADB commands."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Callable

from .adb import (
    AdbController,
    AdbError,
    KeyCommand,
    LongPressCommand,
    SwipeCommand,
    TapCommand,
    TextCommand,
)
from .screen import FrameControlLease, FrameMetadata, FrameRegistry


class ControlError(RuntimeError):
    def __init__(self, code: str, message: str = "Android control was rejected"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FrameReference:
    stream_id: str
    frame_id: str
    display_id: int
    rotation: int
    adb_target: str
    adb_generation: int


def map_normalized_point(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    if (
        isinstance(x, bool)
        or isinstance(y, bool)
        or not isinstance(x, (int, float))
        or not isinstance(y, (int, float))
        or not math.isfinite(float(x))
        or not math.isfinite(float(y))
        or not 0.0 <= x <= 1.0
        or not 0.0 <= y <= 1.0
    ):
        raise ControlError("INVALID_COORDINATES")
    if width < 1 or height < 1:
        raise ControlError("INVALID_FRAME")
    return round(x * (width - 1)), round(y * (height - 1))


class AndroidControlService:
    def __init__(self, adb: AdbController, registry: FrameRegistry, frame_max_age_seconds: float):
        self.adb = adb
        self.registry = registry
        self.frame_max_age_seconds = frame_max_age_seconds

    def _validated_frame(self, owner_id: str, reference: FrameReference) -> FrameMetadata:
        frame = self.registry.current_for(owner_id, reference.stream_id)
        if frame is None:
            raise ControlError("FRAME_REQUIRED")
        self._validate_frame(frame, reference)
        return frame

    def _validate_frame(self, frame: FrameMetadata, reference: FrameReference) -> None:
        if frame.stream_id != reference.stream_id or frame.frame_id != reference.frame_id:
            raise ControlError("STALE_FRAME")
        if frame.rotation is None:
            raise ControlError("ROTATION_UNKNOWN")
        if frame.display_id != reference.display_id or frame.rotation != reference.rotation:
            raise ControlError("ROTATION_MISMATCH")
        if frame.adb_target != reference.adb_target or frame.adb_generation != reference.adb_generation:
            raise ControlError("STALE_FRAME")
        status = self.adb.current_status
        if (
            status.state.value != "available"
            or status.target != frame.adb_target
            or status.generation != frame.adb_generation
        ):
            raise ControlError("STALE_FRAME")
        if time.monotonic() - frame.observed_monotonic > self.frame_max_age_seconds:
            raise ControlError("STALE_FRAME")

    def _validated_lease(self, lease: FrameControlLease, reference: FrameReference) -> FrameMetadata:
        frame = self.registry.frame_for_control(lease)
        if frame is None:
            raise ControlError("STALE_FRAME")
        self._validate_frame(frame, reference)
        return frame

    @staticmethod
    def _authorize(authorization_guard: Callable[[], None] | None) -> None:
        if authorization_guard is not None:
            authorization_guard()

    async def tap(
        self,
        owner_id: str,
        reference: FrameReference,
        x: float,
        y: float,
        *,
        authorization_guard: Callable[[], None] | None = None,
    ) -> None:
        self._authorize(authorization_guard)
        frame = self._validated_frame(owner_id, reference)
        device_x, device_y = map_normalized_point(x, y, frame.width, frame.height)
        await self._execute(owner_id, reference, frame, TapCommand(device_x, device_y), authorization_guard)

    async def swipe(
        self,
        owner_id: str,
        reference: FrameReference,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        duration_ms: int,
        *,
        authorization_guard: Callable[[], None] | None = None,
    ) -> None:
        self._authorize(authorization_guard)
        frame = self._validated_frame(owner_id, reference)
        device_start = map_normalized_point(start_x, start_y, frame.width, frame.height)
        device_end = map_normalized_point(end_x, end_y, frame.width, frame.height)
        await self._execute(owner_id, reference, frame, SwipeCommand(*device_start, *device_end, duration_ms), authorization_guard)

    async def long_press(
        self,
        owner_id: str,
        reference: FrameReference,
        x: float,
        y: float,
        duration_ms: int,
        *,
        authorization_guard: Callable[[], None] | None = None,
    ) -> None:
        self._authorize(authorization_guard)
        frame = self._validated_frame(owner_id, reference)
        device_x, device_y = map_normalized_point(x, y, frame.width, frame.height)
        await self._execute(owner_id, reference, frame, LongPressCommand(device_x, device_y, duration_ms), authorization_guard)

    async def key(
        self,
        owner_id: str,
        reference: FrameReference,
        action: str,
        confirmed: bool = False,
        *,
        authorization_guard: Callable[[], None] | None = None,
    ) -> None:
        if action == "sleep" and not confirmed:
            raise ControlError("CONFIRMATION_REQUIRED")
        self._authorize(authorization_guard)
        frame = self._validated_frame(owner_id, reference)
        await self._execute(owner_id, reference, frame, KeyCommand(action), authorization_guard)

    async def text(
        self,
        owner_id: str,
        reference: FrameReference,
        text: str,
        *,
        authorization_guard: Callable[[], None] | None = None,
    ) -> None:
        self._authorize(authorization_guard)
        frame = self._validated_frame(owner_id, reference)
        await self._execute(owner_id, reference, frame, TextCommand(text), authorization_guard)

    async def _execute(
        self,
        owner_id: str,
        reference: FrameReference,
        frame: FrameMetadata,
        command: TapCommand | SwipeCommand | LongPressCommand | KeyCommand | TextCommand,
        authorization_guard: Callable[[], None] | None,
    ) -> None:
        lease = self.registry.begin_control(owner_id, frame)
        if lease is None:
            raise ControlError("STALE_FRAME")

        def revalidate() -> None:
            self._authorize(authorization_guard)
            self._validated_lease(lease, reference)

        try:
            await self.adb.execute(
                command,
                expected_target=frame.adb_target,
                expected_generation=frame.adb_generation,
                expected_rotation=frame.rotation,
                precondition=revalidate,
            )
        except AdbError as error:
            code = "STALE_FRAME" if error.code in {"ADB_TARGET_CHANGED", "ROTATION_CHANGED"} else error.code
            raise ControlError(code) from error
        finally:
            self.registry.end_control(lease)
