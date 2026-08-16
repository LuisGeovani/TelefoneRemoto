"""Read-only host and Termux metric collection with portable fallbacks."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import platform
import shutil
import socket
import time
from pathlib import Path
from typing import Any

from .config import Settings


def parse_meminfo(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        fields = value.split()
        if fields and fields[0].isdigit():
            result[key] = int(fields[0]) * 1024
    return result


def parse_uptime(text: str) -> float | None:
    try:
        return float(text.split()[0])
    except (IndexError, ValueError):
        return None


def parse_proc_stat(text: str) -> tuple[int, int] | None:
    line = next((item for item in text.splitlines() if item.startswith("cpu ")), None)
    if not line:
        return None
    try:
        values = [int(item) for item in line.split()[1:]]
    except ValueError:
        return None
    if len(values) < 4:
        return None
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return total, idle


def classify_addresses(addresses: list[str]) -> list[str]:
    private: list[str] = []
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed.is_private and not parsed.is_loopback:
            private.append(str(parsed))
    return sorted(set(private))


def _read_proc(name: str) -> str | None:
    try:
        return Path("/proc") .joinpath(name).read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _host_addresses() -> list[str]:
    addresses: list[str] = []
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, type=socket.SOCK_STREAM):
            addresses.append(item[4][0])
    except OSError:
        pass
    return sorted(set(addresses))


async def _port_open(host: str, port: int, timeout: float) -> bool:
    try:
        connection = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(connection, timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except (OSError, asyncio.TimeoutError):
        return False


async def _battery_sample() -> dict[str, Any]:
    command = shutil.which("termux-battery-status")
    if not command:
        return {"state": "unavailable", "reason": "TERMUX_API_NOT_INSTALLED"}
    try:
        process = await asyncio.create_subprocess_exec(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output = await asyncio.wait_for(process.stdout.read(65537), timeout=1.0)
        await asyncio.wait_for(process.wait(), timeout=0.2)
        if len(output) > 65536 or process.returncode != 0:
            return {"state": "unavailable", "reason": "TERMUX_API_FAILED"}
        parsed = json.loads(output.decode("utf-8"))
        return {"state": "ready", "source": "termux-api", "data": parsed}
    except (OSError, asyncio.TimeoutError, json.JSONDecodeError):
        if "process" in locals() and process.returncode is None:
            process.kill()
            await process.wait()
        return {"state": "unavailable", "reason": "TERMUX_API_UNAVAILABLE"}


class MetricsService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.started_monotonic = time.monotonic()

    def uptime(self) -> dict[str, Any]:
        proc_value = _read_proc("uptime")
        seconds = parse_uptime(proc_value) if proc_value else None
        return {"seconds": seconds if seconds is not None else round(time.monotonic() - self.started_monotonic, 2), "source": "procfs" if seconds is not None else "process"}

    def cpu(self) -> dict[str, Any]:
        values = parse_proc_stat(_read_proc("stat") or "")
        return {
            "logical_cores": os.cpu_count(),
            "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
            "proc_stat": {"total_ticks": values[0], "idle_ticks": values[1]} if values else None,
            "source": "procfs" if values else "portable",
        }

    def memory(self) -> dict[str, Any]:
        values = parse_meminfo(_read_proc("meminfo") or "")
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": total - available if total is not None and available is not None else None,
            "source": "procfs" if total is not None else "unavailable",
        }

    def storage(self) -> dict[str, Any]:
        usage = shutil.disk_usage(self.settings.data_dir)
        return {"path": str(self.settings.data_dir), "total_bytes": usage.total, "used_bytes": usage.used, "free_bytes": usage.free, "source": "posix"}

    def system(self) -> dict[str, Any]:
        return {"hostname": socket.gethostname(), "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(), "uptime": self.uptime()}

    async def network(self) -> dict[str, Any]:
        addresses = _host_addresses()
        lan_addresses = classify_addresses(addresses)
        internet = await _port_open(self.settings.internet_probe.host, self.settings.internet_probe.port, self.settings.internet_probe.timeout_seconds)
        ssh = await _port_open("127.0.0.1", self.settings.ssh_probe_port, 0.25)
        adb_available = shutil.which("adb") is not None
        return {
            "addresses": addresses,
            "lan": {"state": "online" if lan_addresses else "degraded", "addresses": lan_addresses, "reason": None if lan_addresses else "NO_PRIVATE_ADDRESS_VISIBLE"},
            "internet": {"state": "online" if internet else "offline", "reason": None if internet else "PROBE_UNREACHABLE"},
            "ssh": {"state": "online" if ssh else "offline", "port": self.settings.ssh_probe_port, "reason": None if ssh else "LOOPBACK_PORT_UNREACHABLE"},
            "adb": {"state": "unavailable", "reason": "NOT_PROBED_IN_M1", "binary_present": adb_available},
            "remote_access": {"state": "offline", "reason": "DISABLED_IN_M1"},
        }

    async def battery(self) -> dict[str, Any]:
        return await _battery_sample()

    async def dashboard(self) -> dict[str, Any]:
        network = await self.network()
        return {
            "server": {"state": "online", "reason": None},
            "system": self.system(),
            "cpu": self.cpu(),
            "ram": self.memory(),
            "storage": self.storage(),
            "network": network,
            "battery": await self.battery(),
        }
