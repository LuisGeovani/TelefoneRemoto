"""PNG screenshot provider, frame registry and bounded latest-frame streaming."""

from __future__ import annotations

import abc
import asyncio
import contextlib
import struct
import time
import uuid
from dataclasses import dataclass

from .adb import AdbController, AdbError

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ScreenError(RuntimeError):
    def __init__(self, code: str, message: str = "Screen provider failed"):
        super().__init__(message)
        self.code = code


def parse_png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ScreenError("INVALID_PNG")
    ihdr_length = struct.unpack(">I", data[8:12])[0]
    if ihdr_length != 13:
        raise ScreenError("INVALID_PNG")
    width, height = struct.unpack(">II", data[16:24])
    if not 1 <= width <= 16384 or not 1 <= height <= 16384:
        raise ScreenError("INVALID_DIMENSIONS")
    return width, height


@dataclass(frozen=True)
class FrameMetadata:
    stream_id: str
    frame_id: str
    width: int
    height: int
    rotation: int | None
    display_id: int
    mime: str
    observed_at: str
    observed_monotonic: float
    adb_target: str
    adb_generation: int

    @property
    def orientation(self) -> str:
        if self.width == self.height:
            return "square"
        return "landscape" if self.width > self.height else "portrait"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "type": "frame",
            "stream_id": self.stream_id,
            "frame_id": self.frame_id,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "display_id": self.display_id,
            "mime": self.mime,
            "orientation": self.orientation,
            "aspect_ratio": self.width / self.height,
            "observed_at": self.observed_at,
            "adb_target": self.adb_target,
            "adb_generation": self.adb_generation,
        }


@dataclass(frozen=True)
class Frame:
    metadata: FrameMetadata
    data: bytes


@dataclass(frozen=True)
class StreamError:
    code: str


StreamItem = Frame | StreamError


class ScreenProvider(abc.ABC):
    @abc.abstractmethod
    async def capture(self, stream_id: str) -> Frame:
        raise NotImplementedError


class AdbScreenProvider(ScreenProvider):
    def __init__(self, adb: AdbController):
        self.adb = adb

    async def capture(self, stream_id: str) -> Frame:
        try:
            capture = await self.adb.capture_screen()
        except AdbError as error:
            raise ScreenError(error.code) from error
        png = capture.png
        width, height = parse_png_dimensions(png)
        metadata = FrameMetadata(
            stream_id=stream_id,
            frame_id=str(uuid.uuid4()),
            width=width,
            height=height,
            rotation=capture.rotation,
            display_id=0,
            mime="image/png",
            observed_at=capture.captured_at,
            observed_monotonic=capture.captured_monotonic,
            adb_target=capture.target,
            adb_generation=capture.generation,
        )
        return Frame(metadata, png)


class MockScreenProvider(ScreenProvider):
    def __init__(self, frames: list[Frame] | None = None, error_code: str | None = None):
        self.frames = list(frames or [])
        self.error_code = error_code
        self.capture_count = 0

    async def capture(self, stream_id: str) -> Frame:
        self.capture_count += 1
        if self.error_code:
            raise ScreenError(self.error_code)
        if not self.frames:
            raise ScreenError("NO_MOCK_FRAME")
        frame = self.frames[min(self.capture_count - 1, len(self.frames) - 1)]
        return Frame(
            FrameMetadata(
                stream_id=stream_id,
                frame_id=frame.metadata.frame_id,
                width=frame.metadata.width,
                height=frame.metadata.height,
                rotation=frame.metadata.rotation,
                display_id=frame.metadata.display_id,
                mime=frame.metadata.mime,
                observed_at=frame.metadata.observed_at,
                observed_monotonic=time.monotonic(),
                adb_target=frame.metadata.adb_target,
                adb_generation=frame.metadata.adb_generation,
            ),
            frame.data,
        )


class LatestFrameQueue:
    """Per-client queue with a strict maximum of one latest item."""

    def __init__(self):
        self._queue: asyncio.Queue[StreamItem] = asyncio.Queue(maxsize=1)
        self.dropped = 0

    def publish(self, item: StreamItem) -> None:
        if self._queue.full():
            self._queue.get_nowait()
            self.dropped += 1
        self._queue.put_nowait(item)

    async def get(self) -> StreamItem:
        return await self._queue.get()

    @property
    def size(self) -> int:
        return self._queue.qsize()


@dataclass(frozen=True)
class StreamSubscription:
    stream_id: str
    queue: LatestFrameQueue


@dataclass(frozen=True)
class FrameControlLease:
    """Internal authorization for one already-validated control request.

    A normal ACK may advance the stream while the request waits for the ADB
    operation gate.  Explicit stream/session invalidation still revokes the
    lease immediately.
    """

    token: str
    owner_id: str
    metadata: FrameMetadata


class FrameRegistry:
    """Stores each session's newest frame acknowledged on its own stream."""

    def __init__(self):
        self._frames: dict[tuple[str, str], FrameMetadata] = {}
        self._deliveries: dict[str, tuple[int, str]] = {}
        self._stream_epochs: dict[str, int] = {}
        self._invalidated_before = 0.0
        self._control_leases: dict[str, FrameControlLease] = {}

    def current_for(self, owner_id: str, stream_id: str | None = None) -> FrameMetadata | None:
        if stream_id is not None:
            return self._frames.get((owner_id, stream_id))
        owned = [frame for (owner, _), frame in self._frames.items() if owner == owner_id]
        return max(owned, key=lambda frame: frame.observed_monotonic, default=None)

    def prepare_delivery(self, metadata: FrameMetadata) -> int:
        epoch = self._stream_epochs.setdefault(metadata.stream_id, 0)
        self._deliveries[metadata.stream_id] = (epoch, metadata.frame_id)
        return epoch

    def confirm(self, owner_id: str, metadata: FrameMetadata, delivery_epoch: int | None = None) -> bool:
        if metadata.observed_monotonic <= self._invalidated_before:
            return False
        if delivery_epoch is not None:
            expected = self._deliveries.get(metadata.stream_id)
            if expected != (delivery_epoch, metadata.frame_id):
                return False
            if self._stream_epochs.get(metadata.stream_id, 0) != delivery_epoch:
                return False
        key = (owner_id, metadata.stream_id)
        current = self._frames.get(key)
        if current is None or metadata.observed_monotonic > current.observed_monotonic:
            self._frames[key] = metadata
        return True

    def begin_control(self, owner_id: str, metadata: FrameMetadata) -> FrameControlLease | None:
        current = self.current_for(owner_id, metadata.stream_id)
        if current is None or current.frame_id != metadata.frame_id:
            return None
        lease = FrameControlLease(str(uuid.uuid4()), owner_id, metadata)
        self._control_leases[lease.token] = lease
        return lease

    def frame_for_control(self, lease: FrameControlLease) -> FrameMetadata | None:
        active = self._control_leases.get(lease.token)
        if active != lease:
            return None
        return active.metadata

    def end_control(self, lease: FrameControlLease) -> None:
        self._control_leases.pop(lease.token, None)

    def invalidate_stream(self, stream_id: str) -> None:
        self._stream_epochs[stream_id] = self._stream_epochs.get(stream_id, 0) + 1
        self._deliveries.pop(stream_id, None)
        self.clear_stream(stream_id)

    def clear_stream(self, stream_id: str) -> None:
        self._frames = {
            key: frame
            for key, frame in self._frames.items()
            if key[1] != stream_id
        }
        self._control_leases = {
            token: lease
            for token, lease in self._control_leases.items()
            if lease.metadata.stream_id != stream_id
        }

    def clear_owner(self, owner_id: str) -> None:
        self._frames = {
            key: frame for key, frame in self._frames.items() if key[0] != owner_id
        }
        self._control_leases = {
            token: lease
            for token, lease in self._control_leases.items()
            if lease.owner_id != owner_id
        }

    def clear_all(self) -> None:
        self._frames.clear()
        self._control_leases.clear()
        self._deliveries.clear()
        self._invalidated_before = time.monotonic()
        for stream_id in tuple(self._stream_epochs):
            self._stream_epochs[stream_id] += 1


class ScreenStreamHub:
    """One low-FPS producer shared by all clients; no capture without clients."""

    def __init__(self, provider: ScreenProvider, fps: float, registry: FrameRegistry, max_clients: int = 2):
        self.provider = provider
        self.fps = fps
        self.registry = registry
        self.max_clients = max_clients
        self._subscribers: set[LatestFrameQueue] = set()
        self._producer: asyncio.Task[None] | None = None
        self._stream_id: str | None = None
        self._lock = asyncio.Lock()

    async def subscribe(self) -> StreamSubscription:
        queue = LatestFrameQueue()
        subscription_id = str(uuid.uuid4())
        async with self._lock:
            if len(self._subscribers) >= self.max_clients:
                raise ScreenError("STREAM_CAPACITY")
            if self._producer is None or self._producer.done():
                self._stream_id = str(uuid.uuid4())
            self._subscribers.add(queue)
            producer_stream_id = self._stream_id
            if self._producer is None or self._producer.done():
                if producer_stream_id is None:
                    raise RuntimeError("stream did not initialize")
                self._producer = asyncio.create_task(self._produce(producer_stream_id), name="s10-screen-producer")
        if producer_stream_id is None:
            raise RuntimeError("stream did not start")
        return StreamSubscription(subscription_id, queue)

    async def unsubscribe(self, subscription: StreamSubscription) -> None:
        task: asyncio.Task[None] | None = None
        async with self._lock:
            self._subscribers.discard(subscription.queue)
            self.registry.invalidate_stream(subscription.stream_id)
            if not self._subscribers and self._producer:
                task = self._producer
                self._producer = None
                self._stream_id = None
                task.cancel()
        if task:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def close(self) -> None:
        task: asyncio.Task[None] | None
        async with self._lock:
            task = self._producer
            self._producer = None
            self._stream_id = None
            self._subscribers.clear()
            if task:
                task.cancel()
            self.registry.clear_all()
        if task:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _produce(self, stream_id: str) -> None:
        interval = 1.0 / self.fps
        while True:
            started = time.monotonic()
            try:
                item: StreamItem = await self.provider.capture(stream_id)
            except ScreenError as error:
                self.registry.clear_all()
                item = StreamError(error.code)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.registry.clear_all()
                item = StreamError("SCREEN_CAPTURE_ERROR")
            for subscriber in tuple(self._subscribers):
                subscriber.publish(item)
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))
