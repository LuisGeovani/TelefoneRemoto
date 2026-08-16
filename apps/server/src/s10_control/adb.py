"""Typed, optional ADB gateway. No arbitrary shell or ADB lifecycle commands."""

from __future__ import annotations

import abc
import asyncio
import re
import shutil
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Awaitable, Callable, Sequence

from .config import AdbConfig

GENERAL_OUTPUT_LIMIT = 256 * 1024
SCREENSHOT_OUTPUT_LIMIT = 24 * 1024 * 1024


class AdbState(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNAUTHORIZED = "unauthorized"
    CONNECTING = "connecting"
    ERROR = "error"


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str
    transport: str
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AdbStatus:
    state: AdbState
    reason: str
    observed_at: str
    generation: int = 0
    target: str | None = None
    transport: str | None = None
    transport_id: str | None = None
    model: str | None = None
    fingerprint: str | None = None
    devices: tuple[AdbDevice, ...] = ()
    mdns_endpoints: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "observed_at": self.observed_at,
            "generation": self.generation,
            "target": self.target,
            "transport": self.transport,
            "transport_id": self.transport_id,
            "model": self.model,
            "fingerprint": self.fingerprint,
            "devices": [
                {"serial": item.serial, "state": item.state, "transport": item.transport, "details": item.details}
                for item in self.devices
            ],
            "mdns_endpoints": list(self.mdns_endpoints),
        }


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class AdbScreenCapture:
    png: bytes
    rotation: int | None
    target: str
    generation: int
    captured_at: str
    captured_monotonic: float


class AdbError(RuntimeError):
    def __init__(self, code: str, message: str = "ADB operation failed"):
        super().__init__(message)
        self.code = code


class AdbOperationKind(str, Enum):
    CONTROL = "control"
    CAPTURE = "capture"
    STATUS = "status"


@dataclass
class _AdbGateWaiter:
    kind: AdbOperationKind
    future: asyncio.Future[None]
    queued_at: float
    granted: bool = False
    cancelled: bool = False


class AdbOperationGate:
    """Bounded fair gate with control priority and capture starvation limits."""

    def __init__(
        self,
        *,
        maximum_waiters: int = 32,
        maximum_control_burst: int = 4,
        minimum_capture_gap_seconds: float = 0.0,
    ):
        self.maximum_waiters = maximum_waiters
        self.maximum_control_burst = maximum_control_burst
        self.minimum_capture_gap_seconds = minimum_capture_gap_seconds
        self._queues: dict[AdbOperationKind, deque[_AdbGateWaiter]] = {
            kind: deque() for kind in AdbOperationKind
        }
        self._active: _AdbGateWaiter | None = None
        self._consecutive_controls = 0
        self._capture_not_before = 0.0
        self._wakeup: asyncio.TimerHandle | None = None

    @property
    def busy(self) -> bool:
        return self._active is not None or any(
            self._valid_waiter(queue) is not None for queue in self._queues.values()
        )

    def reserve_control_window(self, seconds: float) -> None:
        self._capture_not_before = max(self._capture_not_before, time.monotonic() + max(0.0, seconds))
        self._grant_next()

    async def acquire(self, kind: AdbOperationKind, timeout: float) -> None:
        if self._waiting_count() >= self.maximum_waiters:
            raise AdbError("BUSY_TIMEOUT", "ADB operation queue is full")
        loop = asyncio.get_running_loop()
        waiter = _AdbGateWaiter(kind, loop.create_future(), time.monotonic())
        self._queues[kind].append(waiter)
        self._grant_next()
        try:
            await asyncio.wait_for(asyncio.shield(waiter.future), timeout=timeout)
        except asyncio.TimeoutError as error:
            self._cancel_waiter(waiter)
            raise AdbError("BUSY_TIMEOUT", "ADB operation queue timed out") from error
        except BaseException:
            self._cancel_waiter(waiter)
            raise

    def release(self) -> None:
        waiter = self._active
        if waiter is None:
            raise RuntimeError("ADB operation gate is not acquired")
        self._active = None
        if waiter.kind is AdbOperationKind.CAPTURE:
            self._capture_not_before = time.monotonic() + self.minimum_capture_gap_seconds
        self._grant_next()

    def _cancel_waiter(self, waiter: _AdbGateWaiter) -> None:
        waiter.cancelled = True
        if waiter.granted and self._active is waiter:
            self.release()
        else:
            self._grant_next()

    def _waiting_count(self) -> int:
        return sum(
            1
            for queue in self._queues.values()
            for waiter in queue
            if not waiter.cancelled and not waiter.granted
        )

    @staticmethod
    def _valid_waiter(queue: deque[_AdbGateWaiter]) -> _AdbGateWaiter | None:
        while queue and (queue[0].cancelled or queue[0].granted):
            queue.popleft()
        return queue[0] if queue else None

    def _take(self, kind: AdbOperationKind) -> _AdbGateWaiter | None:
        queue = self._queues[kind]
        waiter = self._valid_waiter(queue)
        if waiter is not None:
            queue.popleft()
        return waiter

    def _schedule_capture_wakeup(self, delay: float) -> None:
        if self._wakeup is not None and not self._wakeup.cancelled():
            return
        loop = asyncio.get_running_loop()
        self._wakeup = loop.call_later(delay, self._wake)

    def _wake(self) -> None:
        self._wakeup = None
        self._grant_next()

    def _grant_next(self) -> None:
        if self._active is not None:
            return
        control = self._valid_waiter(self._queues[AdbOperationKind.CONTROL])
        capture = self._valid_waiter(self._queues[AdbOperationKind.CAPTURE])
        status = self._valid_waiter(self._queues[AdbOperationKind.STATUS])
        now = time.monotonic()
        capture_ready = capture is not None and now >= self._capture_not_before

        selected: _AdbGateWaiter | None = None
        if control is not None and not (
            capture_ready and self._consecutive_controls >= self.maximum_control_burst
        ):
            selected = self._take(AdbOperationKind.CONTROL)
        elif capture_ready:
            selected = self._take(AdbOperationKind.CAPTURE)
        elif status is not None:
            selected = self._take(AdbOperationKind.STATUS)
        elif control is not None:
            selected = self._take(AdbOperationKind.CONTROL)
        elif capture is not None:
            self._schedule_capture_wakeup(max(0.0, self._capture_not_before - now))

        if selected is None:
            return
        selected.granted = True
        self._active = selected
        if selected.kind is AdbOperationKind.CONTROL:
            self._consecutive_controls += 1
        else:
            self._consecutive_controls = 0
        if not selected.future.done():
            selected.future.set_result(None)


@dataclass(frozen=True)
class TapCommand:
    x: int
    y: int


@dataclass(frozen=True)
class SwipeCommand:
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration_ms: int


@dataclass(frozen=True)
class LongPressCommand:
    x: int
    y: int
    duration_ms: int


@dataclass(frozen=True)
class KeyCommand:
    action: str


@dataclass(frozen=True)
class TextCommand:
    text: str


AndroidInputCommand = TapCommand | SwipeCommand | LongPressCommand | KeyCommand | TextCommand

KEYCODES = {
    "home": 3,
    "back": 4,
    "recents": 187,
    "enter": 66,
    "volume_up": 24,
    "volume_down": 25,
    "volume_mute": 164,
    "wake": 224,
    "sleep": 223,
}
# Android's ``adb shell`` transport may reconstruct a shell command even when
# the host process is spawned without a shell.  Keep the text alphabet narrow
# enough that replacing spaces with ``%s`` produces a single inert argument.
SAFE_TEXT = re.compile(r"[A-Za-z0-9 .,@_+\-]{1,200}\Z")


def _observed_now() -> str:
    return datetime.now(UTC).isoformat()


def _transport_for(serial: str) -> str:
    if serial.startswith("emulator-"):
        return "emulator"
    if ":" in serial:
        return "tcp"
    return "usb"


def parse_adb_devices(output: str) -> list[AdbDevice]:
    devices: list[AdbDevice] = []
    for raw_line in output.replace("\r", "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        serial, state = fields[0], fields[1]
        if not re.fullmatch(r"[A-Za-z0-9._:\[\]%-]+", serial):
            continue
        details: dict[str, str] = {}
        for value in fields[2:]:
            key, separator, detail = value.partition(":")
            if separator and key and detail:
                details[key] = detail
        devices.append(AdbDevice(serial, state, _transport_for(serial), details))
    return devices


def parse_mdns_services(output: str) -> list[str]:
    endpoints: list[str] = []
    for line in output.replace("\r", "").splitlines():
        if "_adb-tls-connect._tcp" not in line:
            continue
        match = re.search(
            r"((?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+(?:%[A-Za-z0-9._-]+)?\]):[0-9]{1,5})\s*$",
            line.strip(),
        )
        if match:
            endpoints.append(match.group(1))
    return sorted(set(endpoints))


def parse_rotation(output: str) -> int | None:
    patterns = (
        r"SurfaceOrientation:\s*([0-3])",
        r"mCurrentRotation=(?:ROTATION_)?([0-3])",
        r"\brotation\s*[=: ]\s*([0-3])\b",
    )
    for pattern in patterns:
        match = re.search(pattern, output, flags=re.IGNORECASE)
        if match:
            return int(match.group(1)) * 90
    return None


async def run_limited_process(arguments: Sequence[str], timeout: float, output_limit: int) -> ProcessResult:
    if not arguments:
        raise ValueError("arguments cannot be empty")
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def read_limited(stream: asyncio.StreamReader | None, limit: int) -> bytes:
        if stream is None:
            return b""
        data = bytearray()
        while True:
            chunk = await stream.read(min(65536, limit + 1 - len(data)))
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise AdbError("OUTPUT_LIMIT", "ADB output exceeded its configured limit")

    stdout_task: asyncio.Task[bytes] | None = None
    stderr_task: asyncio.Task[bytes] | None = None
    try:
        stdout_task = asyncio.create_task(read_limited(process.stdout, output_limit))
        stderr_task = asyncio.create_task(read_limited(process.stderr, GENERAL_OUTPUT_LIMIT))
        stdout, stderr = await asyncio.wait_for(asyncio.gather(stdout_task, stderr_task), timeout=timeout)
        returncode = await asyncio.wait_for(process.wait(), timeout=0.5)
        return ProcessResult(returncode, stdout, stderr)
    except asyncio.TimeoutError as error:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise AdbError("TIMEOUT", "ADB operation timed out") from error
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        pending = [task for task in (stdout_task, stderr_task) if task is not None and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        raise


Runner = Callable[[Sequence[str], float, int], Awaitable[ProcessResult]]
BinaryResolver = Callable[[], str | None]


class AdbController(abc.ABC):
    @property
    @abc.abstractmethod
    def current_status(self) -> AdbStatus:
        raise NotImplementedError

    @abc.abstractmethod
    async def status(self, force: bool = False) -> AdbStatus:
        raise NotImplementedError

    @abc.abstractmethod
    async def capture_screen(self) -> AdbScreenCapture:
        raise NotImplementedError

    @abc.abstractmethod
    async def display_rotation(self) -> int | None:
        raise NotImplementedError

    @abc.abstractmethod
    async def execute(
        self,
        command: AndroidInputCommand,
        *,
        expected_target: str,
        expected_generation: int,
        expected_rotation: int,
        precondition: Callable[[], None],
    ) -> None:
        raise NotImplementedError


class SubprocessAdbController(AdbController):
    """ADB adapter that always resolves and passes an explicit ``-s`` target."""

    def __init__(
        self,
        config: AdbConfig,
        runner: Runner = run_limited_process,
        binary_resolver: BinaryResolver | None = None,
    ):
        self.config = config
        self._runner = runner
        self._binary_resolver = binary_resolver or (lambda: shutil.which("adb"))
        self._lock = asyncio.Lock()
        self._scheduler = AdbOperationGate()
        self._last_probe_monotonic = 0.0
        self._identity_key: tuple[str, str, str, str, str] | None = None
        self._generation = 0
        self._status = AdbStatus(
            AdbState.CONNECTING if config.enabled else AdbState.UNAVAILABLE,
            "NOT_PROBED" if config.enabled else "DISABLED",
            _observed_now(),
        )

    @property
    def current_status(self) -> AdbStatus:
        return self._status

    def _set_status(self, state: AdbState, reason: str, **values: object) -> AdbStatus:
        if state is AdbState.AVAILABLE:
            identity_key = (
                str(values.get("target", "")),
                str(values.get("transport", "")),
                str(values.get("transport_id", "")),
                str(values.get("model", "")),
                str(values.get("fingerprint", "")),
            )
            if identity_key != self._identity_key:
                self._generation += 1
                self._identity_key = identity_key
        elif state is not AdbState.CONNECTING and self._identity_key is not None:
            self._generation += 1
            self._identity_key = None
        status = AdbStatus(
            state=state,
            reason=reason,
            observed_at=_observed_now(),
            generation=self._generation,
            **values,
        )
        self._status = status
        self._last_probe_monotonic = time.monotonic()
        return status

    async def _run(self, binary: str, arguments: Sequence[str], timeout: float, output_limit: int = GENERAL_OUTPUT_LIMIT) -> ProcessResult:
        return await self._runner((binary, *arguments), timeout, output_limit)

    async def status(self, force: bool = False) -> AdbStatus:
        if not self.config.enabled:
            return self._set_status(AdbState.UNAVAILABLE, "DISABLED")
        age = time.monotonic() - self._last_probe_monotonic
        if not force and age < self.config.status_cache_seconds and self._status.state is not AdbState.CONNECTING:
            return self._status
        async with self._lock:
            age = time.monotonic() - self._last_probe_monotonic
            if not force and age < self.config.status_cache_seconds and self._status.state is not AdbState.CONNECTING:
                return self._status
            binary = self._binary_resolver()
            if not binary:
                return self._set_status(AdbState.UNAVAILABLE, "ADB_BINARY_MISSING")
            # A status refresh is observational. If a bounded capture/input is
            # in flight, keep the last coherent status instead of changing the
            # target generation underneath that operation.
            if self._scheduler.busy:
                return self._status
            try:
                await self._scheduler.acquire(AdbOperationKind.STATUS, self.config.command_timeout_seconds)
                try:
                    self._status = AdbStatus(
                        AdbState.CONNECTING,
                        "PROBING",
                        _observed_now(),
                        generation=self._generation,
                    )
                    device_result = await self._run(binary, ("devices", "-l"), self.config.command_timeout_seconds)
                    if device_result.returncode != 0:
                        return self._status_from_failure(device_result)
                    devices = tuple(parse_adb_devices(device_result.stdout.decode("utf-8", errors="replace")))
                    mdns_endpoints: tuple[str, ...] = ()
                    try:
                        mdns = await self._run(binary, ("mdns", "services"), min(self.config.command_timeout_seconds, 2.0))
                        if mdns.returncode == 0:
                            mdns_endpoints = tuple(parse_mdns_services(mdns.stdout.decode("utf-8", errors="replace")))
                    except (AdbError, OSError):
                        pass
                    selected = self._select_device(devices)
                    common = {"devices": devices, "mdns_endpoints": mdns_endpoints}
                    if selected is None:
                        if self.config.target_serial and any(item.serial == self.config.target_serial and item.state == "unauthorized" for item in devices):
                            return self._set_status(AdbState.UNAUTHORIZED, "AUTHORIZATION_REQUIRED", target=self.config.target_serial, **common)
                        if not self.config.target_serial and any(item.state == "unauthorized" for item in devices):
                            return self._set_status(AdbState.UNAUTHORIZED, "AUTHORIZATION_REQUIRED", **common)
                        reason = "TARGET_NOT_CONNECTED" if self.config.target_serial else "NO_MATCHING_DEVICE"
                        return self._set_status(AdbState.UNAVAILABLE, reason, **common)
                    if selected.state == "unauthorized":
                        return self._set_status(
                            AdbState.UNAUTHORIZED,
                            "AUTHORIZATION_REQUIRED",
                            target=selected.serial,
                            transport=selected.transport,
                            transport_id=selected.details.get("transport_id"),
                            **common,
                        )
                    if selected.state != "device":
                        return self._set_status(
                            AdbState.UNAVAILABLE,
                            "DEVICE_NOT_READY",
                            target=selected.serial,
                            transport=selected.transport,
                            transport_id=selected.details.get("transport_id"),
                            **common,
                        )
                    if not self.config.expected_fingerprint:
                        return self._set_status(
                            AdbState.UNAVAILABLE,
                            "FINGERPRINT_REQUIRED",
                            target=selected.serial,
                            transport=selected.transport,
                            transport_id=selected.details.get("transport_id"),
                            model=selected.details.get("model"),
                            **common,
                        )
                    model = await self._getprop(binary, selected.serial, "ro.product.model")
                    fingerprint = await self._getprop(binary, selected.serial, "ro.build.fingerprint")
                    if model != self.config.expected_model:
                        return self._set_status(
                            AdbState.ERROR,
                            "MODEL_MISMATCH",
                            target=selected.serial,
                            transport=selected.transport,
                            transport_id=selected.details.get("transport_id"),
                            model=model,
                            fingerprint=fingerprint,
                            **common,
                        )
                    if fingerprint != self.config.expected_fingerprint:
                        return self._set_status(
                            AdbState.ERROR,
                            "FINGERPRINT_MISMATCH",
                            target=selected.serial,
                            transport=selected.transport,
                            transport_id=selected.details.get("transport_id"),
                            model=model,
                            fingerprint=fingerprint,
                            **common,
                        )
                    return self._set_status(
                        AdbState.AVAILABLE,
                        "IDENTITY_VERIFIED",
                        target=selected.serial,
                        transport=selected.transport,
                        transport_id=selected.details.get("transport_id"),
                        model=model,
                        fingerprint=fingerprint,
                        **common,
                    )
                finally:
                    self._scheduler.release()
            except AdbError as error:
                if error.code == "BUSY_TIMEOUT":
                    return self._status
                if self._status.state is not AdbState.CONNECTING and self._status.reason == error.code:
                    return self._status
                if error.code == "AUTHORIZATION_REQUIRED":
                    return self._set_status(AdbState.UNAUTHORIZED, error.code)
                return self._set_status(AdbState.ERROR, error.code)
            except OSError:
                return self._set_status(AdbState.ERROR, "PROCESS_ERROR")

    def _select_device(self, devices: tuple[AdbDevice, ...]) -> AdbDevice | None:
        configured: AdbDevice | None = None
        if self.config.target_serial:
            configured = next((item for item in devices if item.serial == self.config.target_serial), None)
            if configured is not None and configured.state in {"device", "unauthorized"}:
                return configured
        matching = [
            item for item in devices
            if item.state == "device"
            and item.details.get("model", "").replace("_", "-") == self.config.expected_model
        ]
        if len(matching) == 1:
            return matching[0]
        # A wireless-debugging port may change.  If there is exactly one ready
        # device, it is safe to inspect its model/fingerprint read-only; actions
        # stay blocked until both identity checks pass.
        ready = [item for item in devices if item.state == "device"]
        if len(ready) == 1:
            return ready[0]
        return configured

    def _status_from_failure(self, result: ProcessResult) -> AdbStatus:
        message = (result.stderr + result.stdout).decode("utf-8", errors="replace").lower()
        if "unauthorized" in message:
            return self._set_status(AdbState.UNAUTHORIZED, "AUTHORIZATION_REQUIRED")
        if "offline" in message:
            return self._set_status(AdbState.UNAVAILABLE, "DEVICE_OFFLINE")
        if "not found" in message or "no devices/emulators" in message or "cannot connect" in message:
            return self._set_status(AdbState.UNAVAILABLE, "TARGET_NOT_CONNECTED")
        return self._set_status(AdbState.ERROR, "ADB_COMMAND_FAILED")

    async def _getprop(self, binary: str, serial: str, property_name: str) -> str:
        result = await self._run(binary, ("-s", serial, "shell", "getprop", property_name), self.config.command_timeout_seconds)
        if result.returncode != 0:
            status = self._status_from_failure(result)
            raise AdbError(status.reason)
        return result.stdout.decode("utf-8", errors="replace").strip()

    async def _verified_status(self) -> tuple[str, AdbStatus]:
        status = await self.status()
        if status.state is not AdbState.AVAILABLE or not status.target:
            raise AdbError(status.reason, "ADB target is unavailable")
        binary = self._binary_resolver()
        if not binary:
            self._set_status(AdbState.UNAVAILABLE, "ADB_BINARY_MISSING")
            raise AdbError("ADB_BINARY_MISSING")
        return binary, status

    def _ensure_same_identity(self, expected: AdbStatus) -> None:
        current = self._status
        if (
            current.state is not AdbState.AVAILABLE
            or current.target != expected.target
            or current.generation != expected.generation
        ):
            raise AdbError("ADB_TARGET_CHANGED")

    async def _display_rotation_unlocked(self, binary: str, target: str) -> int | None:
        result = await self._run(binary, ("-s", target, "shell", "dumpsys", "input"), self.config.command_timeout_seconds)
        if result.returncode != 0:
            status = self._status_from_failure(result)
            raise AdbError(status.reason)
        return parse_rotation(result.stdout.decode("utf-8", errors="replace"))

    async def capture_screen(self) -> AdbScreenCapture:
        binary, status = await self._verified_status()
        target = status.target
        if target is None:
            raise AdbError("TARGET_NOT_CONNECTED")
        await self._scheduler.acquire(AdbOperationKind.CAPTURE, self.config.screenshot_timeout_seconds)
        try:
            self._ensure_same_identity(status)
            before = await self._display_rotation_unlocked(binary, target)
            result = await self._run(binary, ("-s", target, "exec-out", "screencap", "-p"), self.config.screenshot_timeout_seconds, SCREENSHOT_OUTPUT_LIMIT)
            if result.returncode != 0:
                self._status_from_failure(result)
                raise AdbError("SCREENSHOT_FAILED")
            captured_at = _observed_now()
            captured_monotonic = time.monotonic()
            after = await self._display_rotation_unlocked(binary, target)
            self._ensure_same_identity(status)
            if before != after:
                raise AdbError("ROTATION_CHANGED")
            return AdbScreenCapture(
                result.stdout,
                after,
                target,
                status.generation,
                captured_at,
                captured_monotonic,
            )
        finally:
            self._scheduler.release()

    async def display_rotation(self) -> int | None:
        binary, status = await self._verified_status()
        if status.target is None:
            raise AdbError("TARGET_NOT_CONNECTED")
        await self._scheduler.acquire(AdbOperationKind.STATUS, self.config.command_timeout_seconds)
        try:
            self._ensure_same_identity(status)
            return await self._display_rotation_unlocked(binary, status.target)
        finally:
            self._scheduler.release()

    async def execute(
        self,
        command: AndroidInputCommand,
        *,
        expected_target: str,
        expected_generation: int,
        expected_rotation: int,
        precondition: Callable[[], None],
    ) -> None:
        binary, status = await self._verified_status()
        if status.target != expected_target or status.generation != expected_generation:
            raise AdbError("ADB_TARGET_CHANGED")
        arguments = self._input_arguments(command)
        queue_timeout = (
            self.config.screenshot_timeout_seconds
            + (2.0 * self.config.command_timeout_seconds)
            + self._scheduler.minimum_capture_gap_seconds
        )
        await self._scheduler.acquire(AdbOperationKind.CONTROL, queue_timeout)
        try:
            self._ensure_same_identity(status)
            rotation = await self._display_rotation_unlocked(binary, expected_target)
            precondition()
            self._ensure_same_identity(status)
            if rotation is None:
                raise AdbError("ROTATION_UNKNOWN")
            if rotation != expected_rotation:
                raise AdbError("ROTATION_CHANGED")
            result = await self._run(binary, ("-s", expected_target, "shell", *arguments), self.config.command_timeout_seconds)
            if result.returncode != 0:
                self._status_from_failure(result)
                raise AdbError("INPUT_FAILED")
        finally:
            self._scheduler.release()

    @staticmethod
    def _input_arguments(command: AndroidInputCommand) -> tuple[str, ...]:
        def bounded_integer(value: object, minimum: int, maximum: int) -> bool:
            return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum

        if isinstance(command, TapCommand):
            if not bounded_integer(command.x, 0, 16383) or not bounded_integer(command.y, 0, 16383):
                raise AdbError("COMMAND_NOT_ALLOWED")
            return ("input", "tap", str(command.x), str(command.y))
        if isinstance(command, SwipeCommand):
            coordinates = (command.start_x, command.start_y, command.end_x, command.end_y)
            if any(not bounded_integer(value, 0, 16383) for value in coordinates) or not bounded_integer(command.duration_ms, 100, 2000):
                raise AdbError("COMMAND_NOT_ALLOWED")
            return ("input", "swipe", str(command.start_x), str(command.start_y), str(command.end_x), str(command.end_y), str(command.duration_ms))
        if isinstance(command, LongPressCommand):
            if not bounded_integer(command.x, 0, 16383) or not bounded_integer(command.y, 0, 16383) or not bounded_integer(command.duration_ms, 500, 3000):
                raise AdbError("COMMAND_NOT_ALLOWED")
            return ("input", "swipe", str(command.x), str(command.y), str(command.x), str(command.y), str(command.duration_ms))
        if isinstance(command, KeyCommand):
            keycode = KEYCODES.get(command.action)
            if keycode is None:
                raise AdbError("COMMAND_NOT_ALLOWED")
            return ("input", "keyevent", str(keycode))
        if isinstance(command, TextCommand):
            if not isinstance(command.text, str) or not SAFE_TEXT.fullmatch(command.text):
                raise AdbError("TEXT_NOT_ALLOWED")
            return ("input", "text", command.text.replace(" ", "%s"))
        raise AdbError("COMMAND_NOT_ALLOWED")


class MockAdbController(AdbController):
    def __init__(
        self,
        state: AdbState = AdbState.AVAILABLE,
        png: bytes = b"",
        rotation: int | None = 0,
        reason: str = "MOCK",
        target: str = "mock-device",
        generation: int = 1,
    ):
        self.mock_state = state
        self.png = png
        self.rotation = rotation
        self.reason = reason
        self.target = target
        self.generation = generation
        self.commands: list[AndroidInputCommand] = []
        self.capture_count = 0

    @property
    def current_status(self) -> AdbStatus:
        return AdbStatus(
            self.mock_state,
            self.reason,
            _observed_now(),
            generation=self.generation,
            target=self.target if self.mock_state is AdbState.AVAILABLE else None,
            transport="mock",
            transport_id="mock-transport-1",
        )

    async def status(self, force: bool = False) -> AdbStatus:
        del force
        return self.current_status

    async def capture_screen(self) -> AdbScreenCapture:
        if self.mock_state is not AdbState.AVAILABLE:
            raise AdbError(self.reason)
        self.capture_count += 1
        return AdbScreenCapture(
            self.png,
            self.rotation,
            self.target,
            self.generation,
            _observed_now(),
            time.monotonic(),
        )

    async def display_rotation(self) -> int | None:
        if self.mock_state is not AdbState.AVAILABLE:
            raise AdbError(self.reason)
        return self.rotation

    async def execute(
        self,
        command: AndroidInputCommand,
        *,
        expected_target: str,
        expected_generation: int,
        expected_rotation: int,
        precondition: Callable[[], None],
    ) -> None:
        if self.mock_state is not AdbState.AVAILABLE:
            raise AdbError(self.reason)
        SubprocessAdbController._input_arguments(command)
        if expected_target != self.target or expected_generation != self.generation:
            raise AdbError("ADB_TARGET_CHANGED")
        if self.rotation is None:
            raise AdbError("ROTATION_UNKNOWN")
        if expected_rotation != self.rotation:
            raise AdbError("ROTATION_CHANGED")
        precondition()
        self.commands.append(command)


class AdbMonitor:
    """Background status refresh with bounded backoff; it never manages adbd."""

    def __init__(self, controller: AdbController):
        self.controller = controller
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="s10-adb-monitor")

    async def close(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        delay = 1.0
        while True:
            try:
                status = await self.controller.status(force=True)
                delay = 5.0 if status.state is AdbState.AVAILABLE else min(30.0, max(2.0, delay * 2.0))
            except asyncio.CancelledError:
                raise
            except Exception:
                delay = min(30.0, max(2.0, delay * 2.0))
            await asyncio.sleep(delay)
