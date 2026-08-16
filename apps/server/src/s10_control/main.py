"""FastAPI application and API boundary for the local dashboard."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, AsyncIterator

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import AuthService, Principal, SESSION_COOKIE
from .config import ConfigurationError, Settings, load_settings
from .database import open_database
from .metrics import MetricsService

LOGGER = logging.getLogger("s10_control")


class BootstrapExchange(BaseModel):
    token: str = Field(min_length=20, max_length=256)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = open_database(resolved.database_path)
        auth = AuthService(database, resolved)
        bootstrap_created = auth.ensure_bootstrap()
        app.state.database = database
        app.state.auth = auth
        app.state.metrics = MetricsService(resolved)
        if bootstrap_created:
            LOGGER.warning("bootstrap credential created; retrieve it locally with s10-control bootstrap-token")
        try:
            yield
        finally:
            database.close()

    app = FastAPI(title="S10 Control Server", version="0.1.0", lifespan=lifespan)
    app.state.settings = resolved

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception("request_failed", extra={"request_id": request_id, "path": request.url.path})
            response = JSONResponse({"error": {"code": "INTERNAL", "request_id": request_id}}, status_code=500)
        response.headers["X-Request-ID"] = request_id
        LOGGER.info("request_completed", extra={"request_id": request_id, "path": request.url.path, "status": response.status_code, "duration_ms": round((time.monotonic() - started) * 1000, 2)})
        return response

    @app.exception_handler(ConfigurationError)
    async def configuration_error(_: Request, error: ConfigurationError):
        return JSONResponse({"error": {"code": "MISCONFIGURED", "detail": str(error)}}, status_code=503)

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

    def set_session_cookie(response: Response, principal: Principal) -> None:
        response.set_cookie(SESSION_COOKIE, principal.session_id, httponly=True, secure=False, samesite="strict", max_age=resolved.session_ttl_hours * 3600, path="/")

    @app.get("/api/v1/health/live")
    async def live() -> dict[str, str]:
        return {"state": "live"}

    @app.get("/api/v1/health/ready")
    async def ready(request: Request) -> dict[str, object]:
        request.app.state.database.execute("SELECT 1").fetchone()
        return {"state": "ready", "server": "online", "internet_required": False}

    @app.post("/api/v1/auth/bootstrap/exchange")
    async def exchange(payload: BootstrapExchange, response: Response, auth: AuthService = Depends(get_auth)) -> dict[str, str]:
        principal = auth.exchange_bootstrap(payload.token)
        if not principal:
            raise HTTPException(status_code=401, detail={"code": "INVALID_BOOTSTRAP"})
        set_session_cookie(response, principal)
        return {"role": principal.role, "csrf_token": principal.csrf_token}

    @app.get("/api/v1/auth/session")
    async def session(principal: Principal = Depends(current_principal)) -> dict[str, str]:
        return {"user_name": principal.user_name, "role": principal.role, "csrf_token": principal.csrf_token}

    @app.post("/api/v1/auth/logout")
    async def logout(response: Response, principal: Principal = Depends(current_principal), auth: AuthService = Depends(get_auth)) -> dict[str, str]:
        auth.revoke(principal.session_id)
        response.delete_cookie(SESSION_COOKIE, path="/")
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

    static_root = Path(__file__).resolve().parents[2] / "web_dist"
    if static_root.exists():
        app.mount("/assets", StaticFiles(directory=static_root / "assets"), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str):
            candidate = static_root / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_root / "index.html")

    return app
