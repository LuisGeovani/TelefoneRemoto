"""FastAPI boundary for the local dashboard, screen stream and typed controls."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import math
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, AsyncIterator, Literal
from urllib.parse import urlsplit

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, StrictBool, constr, validator

from .adb import AdbController, AdbMonitor, SubprocessAdbController
from .android_control import AndroidControlService, ControlError, FrameReference
from .auth import AuthError, AuthService, MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, Principal, SESSION_COOKIE
from .config import ConfigurationError, Settings, load_settings
from .database import open_database
from .metrics import MetricsService
from .screen import AdbScreenProvider, Frame, FrameRegistry, ScreenError, ScreenProvider, ScreenStreamHub, StreamError

LOGGER = logging.getLogger("s10_control")
Identifier = constr(strict=True, min_length=1, max_length=80, regex=r"^[A-Za-z0-9-]+$")
SafeText = constr(strict=True, min_length=1, max_length=200, regex=r"^[A-Za-z0-9 .,@_+\-]+$")
AdbTarget = constr(strict=True, min_length=1, max_length=200, regex=r"^[A-Za-z0-9._:\[\]%-]+$")
BootstrapToken = constr(strict=True, min_length=20, max_length=256)
Username = constr(strict=True, min_length=1, max_length=64, regex=r"^[A-Za-z0-9._-]+$")
Password = constr(strict=True, min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
LoginText = constr(strict=True, min_length=0, max_length=MAX_PASSWORD_LENGTH)


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"


class SetupRequest(StrictModel):
    token: BootstrapToken
    username: Username
    password: Password
    password_confirmation: Password


class LoginRequest(StrictModel):
    username: LoginText
    password: LoginText


class RecoveryRequest(StrictModel):
    token: BootstrapToken
    password: Password
    password_confirmation: Password


class FrameRequest(StrictModel):
    stream_id: Identifier
    frame_id: Identifier
    display_id: Literal[0]
    rotation: Literal[0, 90, 180, 270]
    adb_target: AdbTarget
    adb_generation: int = Field(ge=1)

    @validator("display_id", "rotation", "adb_generation", pre=True)
    def strict_frame_integer(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("frame integers must be JSON integers")
        return value

    def reference(self) -> FrameReference:
        return FrameReference(
            self.stream_id,
            self.frame_id,
            self.display_id,
            self.rotation,
            self.adb_target,
            self.adb_generation,
        )


class TapRequest(FrameRequest):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)

    @validator("x", "y", pre=True)
    def strict_coordinate(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("coordinates must be finite JSON numbers")
        return value


class SwipeRequest(FrameRequest):
    start_x: float = Field(ge=0.0, le=1.0)
    start_y: float = Field(ge=0.0, le=1.0)
    end_x: float = Field(ge=0.0, le=1.0)
    end_y: float = Field(ge=0.0, le=1.0)
    duration_ms: int = Field(ge=100, le=2000)

    @validator("start_x", "start_y", "end_x", "end_y", pre=True)
    def strict_coordinate(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("coordinates must be finite JSON numbers")
        return value

    @validator("duration_ms", pre=True)
    def strict_duration(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("duration must be a JSON integer")
        return value


class LongPressRequest(FrameRequest):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    duration_ms: int = Field(ge=500, le=3000)

    @validator("x", "y", pre=True)
    def strict_coordinate(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("coordinates must be finite JSON numbers")
        return value

    @validator("duration_ms", pre=True)
    def strict_duration(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("duration must be a JSON integer")
        return value


class KeyRequest(FrameRequest):
    action: Literal["home", "back", "recents", "enter", "volume_up", "volume_down", "volume_mute", "wake", "sleep"]
    confirmed: StrictBool = False


class TextRequest(FrameRequest):
    text: SafeText


class ActionRateLimiter:
    def __init__(self, maximum: int = 12, window_seconds: float = 2.0):
        self.maximum = maximum
        self.window_seconds = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def allow(self, principal: Principal) -> bool:
        async with self._lock:
            key = principal.session_id.split(".", 1)[0]
            now = time.monotonic()
            events = self._events[key]
            while events and now - events[0] > self.window_seconds:
                events.popleft()
            if len(events) >= self.maximum:
                return False
            events.append(now)
            return True


class LoginRateLimiter:
    def __init__(self, maximum: int = 5, window_seconds: float = 60.0, max_keys: int = 256):
        self.maximum = maximum
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._failures: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def claim(self, key: str) -> bool:
        async with self._lock:
            now = time.monotonic()
            failures = self._failures.get(key)
            if failures is not None:
                while failures and now - failures[0] > self.window_seconds:
                    failures.popleft()
                if len(failures) >= self.maximum:
                    return False
            elif len(self._failures) >= self.max_keys:
                self._failures.pop(next(iter(self._failures)))
            self._failures.setdefault(key, deque()).append(now)
            return True

    async def succeeded(self, key: str) -> None:
        async with self._lock:
            self._failures.pop(key, None)


def _same_origin(origin: str | None, host: str | None) -> bool:
    if not origin or not host:
        return False
    parsed = urlsplit(origin)
    return (
        parsed.scheme in {"http", "https"}
        and parsed.netloc.lower() == host.lower()
        and not parsed.username
        and parsed.path in {"", "/"}
        and not parsed.query
        and not parsed.fragment
    )


def _owner_id(principal: Principal) -> str:
    return principal.session_id.split(".", 1)[0]


async def _receive_ack(websocket: WebSocket, timeout: float) -> dict[str, object] | None:
    message = await asyncio.wait_for(websocket.receive(), timeout=timeout)
    if message.get("type") == "websocket.disconnect":
        raise WebSocketDisconnect(message.get("code", 1000))
    text = message.get("text")
    if not isinstance(text, str) or len(text) > 512:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def create_app(
    settings: Settings | None = None,
    adb_controller: AdbController | None = None,
    screen_provider: ScreenProvider | None = None,
) -> FastAPI:
    resolved = settings or load_settings()
    adb = adb_controller or SubprocessAdbController(resolved.adb)
    provider = screen_provider or AdbScreenProvider(adb)
    registry = FrameRegistry()
    stream_hub = ScreenStreamHub(provider, resolved.screen.fps, registry, resolved.screen.max_clients)
    controls = AndroidControlService(adb, registry, resolved.screen.frame_max_age_seconds)
    adb_monitor = AdbMonitor(adb)
    metrics = MetricsService(resolved, adb)
    limiter = ActionRateLimiter()
    login_limiter = LoginRateLimiter()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = open_database(resolved.database_path)
        auth = AuthService(database, resolved)
        bootstrap_created = auth.ensure_bootstrap() if not auth.has_account() else None
        app.state.database = database
        app.state.auth = auth
        app.state.metrics = metrics
        app.state.adb = adb
        app.state.screen_hub = stream_hub
        app.state.frame_registry = registry
        adb_monitor.start()
        if bootstrap_created:
            LOGGER.warning("bootstrap credential created; retrieve it locally with s10-control bootstrap-token")
        try:
            yield
        finally:
            await stream_hub.close()
            await adb_monitor.close()
            database.close()

    app = FastAPI(title="S10 Control Server", version="0.2.2", lifespan=lifespan)
    app.state.settings = resolved

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        routed_path = str(request.scope.get("path", ""))
        started = time.monotonic()
        metrics.observe_local_address(request.scope.get("server"))
        if "range" in request.headers:
            response = JSONResponse(
                {"error": {"code": "RANGE_NOT_SUPPORTED", "request_id": request_id}},
                status_code=416,
            )
            response.headers["Accept-Ranges"] = "none"
        else:
            try:
                response = await call_next(request)
            except Exception:
                LOGGER.exception("request_failed", extra={"request_id": request_id, "path": routed_path})
                response = JSONResponse({"error": {"code": "INTERNAL", "request_id": request_id}}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if routed_path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        LOGGER.info("request_completed", extra={"request_id": request_id, "path": routed_path, "status": response.status_code, "duration_ms": round((time.monotonic() - started) * 1000, 2)})
        return response

    @app.exception_handler(ConfigurationError)
    async def configuration_error(_: Request, error: ConfigurationError):
        return JSONResponse({"error": {"code": "MISCONFIGURED", "detail": str(error)}}, status_code=503)

    @app.exception_handler(ControlError)
    async def control_error(_: Request, error: ControlError):
        stale_codes = {"STALE_FRAME", "ROTATION_MISMATCH", "ROTATION_UNKNOWN", "FRAME_REQUIRED"}
        provider_codes = {
            "ADB_BINARY_MISSING", "ADB_COMMAND_FAILED", "AUTHORIZATION_REQUIRED", "BUSY_TIMEOUT", "DISABLED",
            "DEVICE_NOT_READY", "DEVICE_OFFLINE", "FINGERPRINT_MISMATCH",
            "FINGERPRINT_REQUIRED", "INPUT_FAILED", "MODEL_MISMATCH",
            "NO_MATCHING_DEVICE", "OUTPUT_LIMIT", "PROCESS_ERROR", "ROTATION_PROBE_FAILED",
            "TARGET_NOT_CONNECTED", "TIMEOUT",
        }
        status_code = (
            401 if error.code == "UNAUTHORIZED"
            else 403 if error.code == "FORBIDDEN"
            else 429 if error.code == "RATE_LIMITED"
            else 409 if error.code in stale_codes
            else 503 if error.code in provider_codes
            else 400
        )
        return JSONResponse({"error": {"code": error.code}}, status_code=status_code)

    def get_auth(request: Request) -> AuthService:
        return request.app.state.auth

    def current_principal(
        session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
        auth: AuthService = Depends(get_auth),
    ) -> Principal:
        principal = auth.principal_for_cookie(session)
        if not principal:
            raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED"})
        return principal

    async def csrf_principal(request: Request, principal: Principal = Depends(current_principal)) -> Principal:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), principal.csrf_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_REJECTED"})
        if not _same_origin(request.headers.get("Origin"), request.headers.get("Host")):
            raise HTTPException(status_code=403, detail={"code": "ORIGIN_REJECTED"})
        return principal

    async def control_principal(request: Request, principal: Principal = Depends(csrf_principal)) -> Principal:
        if principal.role != "admin":
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN"})
        if not await limiter.allow(principal):
            raise ControlError("RATE_LIMITED")
        return principal

    def set_session_cookie(response: Response, principal: Principal) -> None:
        ttl_seconds = resolved.session_ttl_hours * 3600
        response.set_cookie(
            SESSION_COOKIE,
            principal.session_id,
            httponly=True,
            secure=resolved.cookie_secure,
            samesite="strict",
            max_age=ttl_seconds,
            expires=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
            path="/",
        )

    def require_same_origin(request: Request) -> None:
        if not _same_origin(request.headers.get("Origin"), request.headers.get("Host")):
            raise HTTPException(status_code=403, detail={"code": "ORIGIN_REJECTED"})

    def auth_failure(error: AuthError) -> HTTPException:
        status = 409 if error.code in {"ACCOUNT_ALREADY_CONFIGURED", "ACCOUNT_NOT_CONFIGURED"} else 401 if error.code == "INVALID_BOOTSTRAP" else 400
        return HTTPException(status_code=status, detail={"code": error.code})

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"state": "live"}

    @app.get("/api/v1/health/ready")
    async def ready(request: Request) -> dict[str, object]:
        request.app.state.database.execute("SELECT 1").fetchone()
        return {"state": "ready", "server": "online", "internet_required": False, "adb_required": False}

    @app.get("/api/v1/auth/state")
    async def auth_state(auth: AuthService = Depends(get_auth)) -> dict[str, bool]:
        return {"configured": auth.has_account()}

    @app.post("/api/v1/auth/setup")
    async def setup(payload: SetupRequest, request: Request, response: Response, auth: AuthService = Depends(get_auth)) -> dict[str, str]:
        require_same_origin(request)
        if payload.password != payload.password_confirmation:
            raise HTTPException(status_code=400, detail={"code": "PASSWORD_MISMATCH"})
        try:
            principal = auth.setup_account(payload.token, payload.username, payload.password)
        except AuthError as error:
            raise auth_failure(error) from error
        set_session_cookie(response, principal)
        return {"user_name": principal.user_name, "role": principal.role, "csrf_token": principal.csrf_token}

    @app.post("/api/v1/auth/login")
    async def login(payload: LoginRequest, request: Request, response: Response, auth: AuthService = Depends(get_auth)) -> dict[str, str]:
        require_same_origin(request)
        client = request.client.host if request.client else "unknown"
        key = f"login:{client}"
        if not await login_limiter.claim(key):
            raise HTTPException(status_code=429, detail={"code": "RATE_LIMITED"})
        principal = auth.authenticate(payload.username, payload.password)
        if not principal:
            raise HTTPException(status_code=401, detail={"code": "INVALID_CREDENTIALS"})
        await login_limiter.succeeded(key)
        set_session_cookie(response, principal)
        return {"user_name": principal.user_name, "role": principal.role, "csrf_token": principal.csrf_token}

    @app.post("/api/v1/auth/recovery")
    async def recovery(payload: RecoveryRequest, request: Request, response: Response, auth: AuthService = Depends(get_auth)) -> dict[str, str]:
        require_same_origin(request)
        if payload.password != payload.password_confirmation:
            raise HTTPException(status_code=400, detail={"code": "PASSWORD_MISMATCH"})
        try:
            principal = auth.recover_account(payload.token, payload.password)
        except AuthError as error:
            raise auth_failure(error) from error
        set_session_cookie(response, principal)
        return {"user_name": principal.user_name, "role": principal.role, "csrf_token": principal.csrf_token}

    @app.get("/api/v1/auth/session")
    async def session(principal: Principal = Depends(current_principal)) -> dict[str, str]:
        return {"user_name": principal.user_name, "role": principal.role, "csrf_token": principal.csrf_token}

    @app.post("/api/v1/auth/logout")
    async def logout(response: Response, principal: Principal = Depends(csrf_principal), auth: AuthService = Depends(get_auth)) -> dict[str, str]:
        auth.revoke(principal.session_id)
        registry.clear_owner(_owner_id(principal))
        response.delete_cookie(
            SESSION_COOKIE,
            path="/",
            secure=resolved.cookie_secure,
            httponly=True,
            samesite="strict",
        )
        return {"state": "logged_out"}

    @app.get("/api/v1/status")
    async def status(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return await request.app.state.metrics.dashboard()

    @app.get("/api/v1/system")
    async def system(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return request.app.state.metrics.system()

    @app.get("/api/v1/cpu")
    async def cpu(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return request.app.state.metrics.cpu()

    @app.get("/api/v1/ram")
    async def ram(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return request.app.state.metrics.memory()

    @app.get("/api/v1/storage")
    async def storage(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return request.app.state.metrics.storage()

    @app.get("/api/v1/uptime")
    async def uptime(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return request.app.state.metrics.uptime()

    @app.get("/api/v1/network")
    async def network(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return await request.app.state.metrics.network()

    @app.get("/api/v1/battery")
    async def battery(request: Request, _: Principal = Depends(current_principal)) -> dict[str, object]:
        return await request.app.state.metrics.battery()

    @app.get("/api/v1/adb/status")
    async def adb_status(_: Principal = Depends(current_principal)) -> dict[str, object]:
        return {"support_class": "experimental", **adb.current_status.to_dict()}

    @app.get("/api/v1/screen/status")
    async def screen_status(principal: Principal = Depends(current_principal)) -> dict[str, object]:
        frame = registry.current_for(_owner_id(principal))
        return {
            "support_class": "experimental",
            "adb": adb.current_status.to_dict(),
            "fps": resolved.screen.fps,
            "max_clients": resolved.screen.max_clients,
            "last_confirmed_frame": frame.to_dict() if frame else None,
        }

    async def run_control(action: str, operation) -> dict[str, object]:
        await operation
        return {"state": "unverified", "action": action, "postcondition_verified": False}

    def ensure_control_authorized(auth: AuthService, principal: Principal) -> None:
        role = auth.active_session_role(principal.session_id)
        if role is None:
            registry.clear_owner(_owner_id(principal))
            raise ControlError("UNAUTHORIZED")
        if role not in {"operator", "admin"}:
            registry.clear_owner(_owner_id(principal))
            raise ControlError("FORBIDDEN")

    @app.post("/api/v1/android/tap")
    async def tap(payload: TapRequest, principal: Principal = Depends(control_principal), auth: AuthService = Depends(get_auth)) -> dict[str, object]:
        guard = lambda: ensure_control_authorized(auth, principal)
        return await run_control("tap", controls.tap(_owner_id(principal), payload.reference(), payload.x, payload.y, authorization_guard=guard))

    @app.post("/api/v1/android/swipe")
    async def swipe(payload: SwipeRequest, principal: Principal = Depends(control_principal), auth: AuthService = Depends(get_auth)) -> dict[str, object]:
        guard = lambda: ensure_control_authorized(auth, principal)
        return await run_control("swipe", controls.swipe(_owner_id(principal), payload.reference(), payload.start_x, payload.start_y, payload.end_x, payload.end_y, payload.duration_ms, authorization_guard=guard))

    @app.post("/api/v1/android/long-press")
    async def long_press(payload: LongPressRequest, principal: Principal = Depends(control_principal), auth: AuthService = Depends(get_auth)) -> dict[str, object]:
        guard = lambda: ensure_control_authorized(auth, principal)
        return await run_control("long_press", controls.long_press(_owner_id(principal), payload.reference(), payload.x, payload.y, payload.duration_ms, authorization_guard=guard))

    @app.post("/api/v1/android/key")
    async def key(payload: KeyRequest, principal: Principal = Depends(control_principal), auth: AuthService = Depends(get_auth)) -> dict[str, object]:
        guard = lambda: ensure_control_authorized(auth, principal)
        return await run_control(payload.action, controls.key(_owner_id(principal), payload.reference(), payload.action, payload.confirmed, authorization_guard=guard))

    @app.post("/api/v1/android/text")
    async def text(payload: TextRequest, principal: Principal = Depends(control_principal), auth: AuthService = Depends(get_auth)) -> dict[str, object]:
        guard = lambda: ensure_control_authorized(auth, principal)
        return await run_control("text", controls.text(_owner_id(principal), payload.reference(), payload.text, authorization_guard=guard))

    @app.websocket("/api/v1/screen/ws")
    async def screen_socket(websocket: WebSocket) -> None:
        auth: AuthService = websocket.app.state.auth
        principal = auth.principal_for_cookie(websocket.cookies.get(SESSION_COOKIE))
        if not principal:
            await websocket.close(code=4401, reason="UNAUTHORIZED")
            return
        if not _same_origin(websocket.headers.get("origin"), websocket.headers.get("host")):
            await websocket.close(code=4403, reason="ORIGIN_REJECTED")
            return
        await websocket.accept()
        owner_id = _owner_id(principal)
        try:
            subscription = await stream_hub.subscribe()
        except ScreenError as error:
            await websocket.send_json({"schema_version": 1, "type": "stream_error", "code": error.code, "adb": adb.current_status.to_dict()})
            await websocket.close(code=4429, reason=error.code)
            return
        socket_timeout = 5.0
        try:
            await asyncio.wait_for(websocket.send_json({
                "schema_version": 1,
                "type": "stream_status",
                "state": "connected",
                "stream_id": subscription.stream_id,
                "fps": resolved.screen.fps,
                "frame_max_age_seconds": resolved.screen.frame_max_age_seconds,
                "adb": adb.current_status.to_dict(),
            }), timeout=socket_timeout)
            while True:
                try:
                    item = await asyncio.wait_for(subscription.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if not auth.is_session_active(principal.session_id):
                        registry.clear_owner(owner_id)
                        await websocket.close(code=4401, reason="SESSION_REVOKED")
                        return
                    continue
                if not auth.is_session_active(principal.session_id):
                    registry.clear_owner(owner_id)
                    await websocket.close(code=4401, reason="SESSION_REVOKED")
                    return
                if isinstance(item, StreamError):
                    await asyncio.wait_for(websocket.send_json({"schema_version": 1, "type": "stream_error", "code": item.code, "adb": adb.current_status.to_dict()}), timeout=socket_timeout)
                    continue
                if not isinstance(item, Frame):
                    continue
                metadata = replace(item.metadata, stream_id=subscription.stream_id)
                delivery_epoch = registry.prepare_delivery(metadata)
                await asyncio.wait_for(websocket.send_json(metadata.to_dict()), timeout=socket_timeout)
                await asyncio.wait_for(websocket.send_bytes(item.data), timeout=socket_timeout)
                ack = await _receive_ack(websocket, socket_timeout)
                expected = {"type": "frame_ack", "stream_id": metadata.stream_id, "frame_id": metadata.frame_id}
                if not isinstance(ack, dict) or set(ack) != set(expected) or any(ack.get(key) != value for key, value in expected.items()):
                    await websocket.close(code=4400, reason="INVALID_ACK")
                    return
                if not auth.is_session_active(principal.session_id):
                    registry.clear_owner(owner_id)
                    await websocket.close(code=4401, reason="SESSION_REVOKED")
                    return
                if not registry.confirm(owner_id, metadata, delivery_epoch):
                    await websocket.close(code=4400, reason="STALE_FRAME_ACK")
                    return
                await asyncio.wait_for(websocket.send_json({
                    "schema_version": 1,
                    "type": "frame_acknowledged",
                    "stream_id": metadata.stream_id,
                    "frame_id": metadata.frame_id,
                }), timeout=socket_timeout)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        finally:
            await stream_hub.unsubscribe(subscription)

    static_root = (Path(__file__).resolve().parents[2] / "web_dist").resolve()
    assets_root = static_root / "assets"
    if static_root.exists() and assets_root.exists():
        @app.get("/{path:path}")
        async def spa(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
            relative = Path(path)
            if path and not relative.is_absolute() and ".." not in relative.parts:
                candidate = (static_root / relative).resolve()
                if candidate.is_relative_to(static_root) and candidate.is_file():
                    return FileResponse(candidate)
            return FileResponse(static_root / "index.html")

    return app
