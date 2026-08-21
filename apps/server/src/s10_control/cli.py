"""Local-only command line entry point."""

from __future__ import annotations

import argparse
import json
import logging
import sys

import uvicorn

from . import __version__
from .auth import AuthService
from .config import ConfigurationError, load_settings
from .database import open_database
from .main import create_app


GRACEFUL_SHUTDOWN_SECONDS = 5


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname.lower(), "message": record.getMessage(), "logger": record.name}
        for field in ("request_id", "path", "status", "duration_ms"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def _auth_service() -> AuthService:
    settings = load_settings()
    return AuthService(open_database(settings.database_path), settings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="s10-control")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("serve", help="serve the LAN dashboard")
    subcommands.add_parser("version", help="print version")
    subcommands.add_parser("bootstrap-token", help="print an unconsumed bootstrap token locally")
    auth = subcommands.add_parser("auth", help="local authentication recovery")
    auth_commands = auth.add_subparsers(dest="auth_command", required=True)
    auth_commands.add_parser("status", help="show whether the single admin account is configured")
    reset = auth_commands.add_parser("reset", help="invalidate sessions and create a recovery bootstrap token")
    reset.add_argument("--yes", action="store_true", help="confirm session invalidation")
    args = parser.parse_args(argv)
    try:
        if args.command == "version":
            print(__version__)
            return 0
        if args.command == "bootstrap-token":
            service = _auth_service()
            try:
                print(service.local_bootstrap_token())
            finally:
                service.connection.close()
            return 0
        if args.command == "auth" and args.auth_command == "status":
            service = _auth_service()
            try:
                status = service.account_status()
                print(f"configured: {'true' if status.configured else 'false'}")
                if status.username is not None:
                    print(f"username: {status.username}")
            finally:
                service.connection.close()
            return 0
        if args.command == "auth" and args.auth_command == "reset":
            if not args.yes:
                print("Refusing to invalidate sessions without --yes.", file=sys.stderr)
                return 2
            service = _auth_service()
            try:
                token = service.ensure_bootstrap(lifetime_seconds=15 * 60, force=True)
                print(token)
            finally:
                service.connection.close()
            return 0
        if args.command == "serve":
            configure_logging()
            settings = load_settings()
            uvicorn.run(
                create_app(settings),
                host=settings.host,
                port=settings.port,
                loop="asyncio",
                http="h11",
                ws="wsproto",
                log_config=None,
                timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
            )
            return 0
    except ConfigurationError as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
