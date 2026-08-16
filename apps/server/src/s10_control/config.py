"""Portable, validated configuration for the server."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "listen": {"host": "0.0.0.0", "port": 8080},
    "session_ttl_hours": 24,
    "internet_probe": {"host": "1.1.1.1", "port": 53, "timeout_seconds": 1.0},
    "ssh_probe_port": 8022,
}


@dataclass(frozen=True)
class ProbeConfig:
    host: str
    port: int
    timeout_seconds: float


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    database_path: Path
    bootstrap_path: Path
    host: str
    port: int
    session_ttl_hours: int
    internet_probe: ProbeConfig
    ssh_probe_port: int


class ConfigurationError(ValueError):
    """Raised when a local configuration file is invalid."""


def _default_data_dir() -> Path:
    configured = os.environ.get("S10_CONTROL_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    state_home = os.environ.get("XDG_STATE_HOME")
    root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "share"
    return (root / "s10-control").resolve()


def _chmod_private(path: Path) -> None:
    if os.name != "nt":
        path.chmod(0o600)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _chmod_private(temporary)
        os.replace(temporary, path)
        _chmod_private(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _expect_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be an object")
    return value


def _read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        atomic_write_json(path, DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return _expect_mapping(json.load(handle), "configuration")
    except json.JSONDecodeError as error:
        raise ConfigurationError(f"configuration JSON is invalid: {error.msg}") from error


def _positive_int(value: object, label: str, maximum: int = 65535) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
        raise ConfigurationError(f"{label} must be an integer between 1 and {maximum}")
    return value


def load_settings(data_dir: Path | None = None) -> Settings:
    root = (data_dir or _default_data_dir()).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        root.chmod(0o700)
    config_path = root / "config.json"
    raw = _read_config(config_path)
    listen = _expect_mapping(raw.get("listen"), "listen")
    probe = _expect_mapping(raw.get("internet_probe"), "internet_probe")
    host = listen.get("host")
    if not isinstance(host, str) or not host:
        raise ConfigurationError("listen.host must be a non-empty string")
    probe_host = probe.get("host")
    if not isinstance(probe_host, str) or not probe_host:
        raise ConfigurationError("internet_probe.host must be a non-empty string")
    timeout = probe.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 10:
        raise ConfigurationError("internet_probe.timeout_seconds must be between 0.1 and 10")
    return Settings(
        data_dir=root,
        config_path=config_path,
        database_path=root / "s10-control.sqlite3",
        bootstrap_path=root / "bootstrap.token",
        host=host,
        port=_positive_int(listen.get("port"), "listen.port"),
        session_ttl_hours=_positive_int(raw.get("session_ttl_hours"), "session_ttl_hours", 24 * 31),
        internet_probe=ProbeConfig(probe_host, _positive_int(probe.get("port"), "internet_probe.port"), float(timeout)),
        ssh_probe_port=_positive_int(raw.get("ssh_probe_port"), "ssh_probe_port"),
    )
