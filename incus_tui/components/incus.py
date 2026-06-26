"""Thin wrapper around the `incus` CLI used by the TUI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass


class IncusError(Exception):
    """Raised when an `incus` command fails or is unavailable."""


_NAME_RE = re.compile(r"^[a-zA-Z0-9-]+$")
_MEMORY_RE = re.compile(r"^\d+(\.\d+)?(MiB|GiB|TiB|MB|GB|TB)$", re.IGNORECASE)


@dataclass(frozen=True)
class Container:
    name: str
    status: str
    type: str
    ipv4: str
    ipv6: str

    @property
    def is_running(self) -> bool:
        return self.status.lower() == "running"


def _incus_path() -> str:
    path = shutil.which("incus")
    if path is None:
        raise IncusError("The `incus` command was not found on PATH.")
    return path


def _global_addresses(state: dict, family: str) -> list[str]:
    """Return the global-scope addresses of the given family across all NICs."""
    addresses = []
    for iface, info in (state.get("network") or {}).items():
        if iface == "lo":
            continue
        for addr in info.get("addresses", []):
            if addr.get("family") == family and addr.get("scope") == "global":
                addresses.append(addr["address"])
    return addresses


def list_containers() -> list[Container]:
    """Return the instances reported by `incus list --format json`."""
    try:
        result = subprocess.run(
            [_incus_path(), "list", "--format", "json"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:  # pragma: no cover - defensive
        raise IncusError(f"Failed to run incus: {exc}") from exc

    if result.returncode != 0:
        message = result.stderr.strip() or "incus list failed"
        raise IncusError(message)

    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise IncusError(f"Could not parse incus output: {exc}") from exc

    containers = []
    for item in data:
        state = item.get("state") or {}
        ipv4 = _global_addresses(state, "inet")
        ipv6 = _global_addresses(state, "inet6")
        containers.append(
            Container(
                name=item.get("name", ""),
                status=item.get("status", "Unknown"),
                type=item.get("type", "container"),
                ipv4=", ".join(ipv4),
                ipv6=", ".join(ipv6),
            )
        )
    containers.sort(key=lambda c: c.name)
    return containers


def mount_command(name: str, target: str) -> list[str]:
    """Command that mounts the container root onto ``target`` via SFTP."""
    return [_incus_path(), "file", "mount", f"{name}/", target]


def shell_command(name: str) -> list[str]:
    """Command that opens an interactive shell inside the container via incus."""
    return [_incus_path(), "shell", name]


def ssh_command(user: str, host: str) -> list[str]:
    """Command that opens an SSH session to the container's address."""
    target = f"{user}@{host}" if user else host
    return ["ssh", target]


def validate_instance_name(name: str) -> str | None:
    """Return an error message if ``name`` is not a valid instance name."""
    if not name:
        return "Name is required."
    if len(name) > 63:
        return "Name must be at most 63 characters."
    if not _NAME_RE.match(name):
        return "Use only letters, numbers and hyphens."
    if name.startswith("-") or name.endswith("-"):
        return "Name cannot start or end with a hyphen."
    if name.isdigit():
        return "Name cannot be only numbers."
    return None


def validate_memory(value: str) -> str | None:
    """Return an error message if ``value`` is not a valid memory limit."""
    if _MEMORY_RE.match(value):
        return None
    return "Memory must look like 512MiB, 2GiB or 4GB."


def normalize_image(image: str) -> str:
    """Default a bare image reference to the public ``images:`` remote."""
    image = image.strip()
    if ":" in image:
        return image
    return f"images:{image}"


def launch_command(
    image: str,
    name: str,
    *,
    cpu: str | None = None,
    memory: str | None = None,
    vm: bool = False,
) -> list[str]:
    """Build an ``incus launch`` command for the given configuration."""
    cmd = [_incus_path(), "launch", image, name]
    if vm:
        cmd.append("--vm")
    if cpu:
        cmd += ["-c", f"limits.cpu={cpu}"]
    if memory:
        cmd += ["-c", f"limits.memory={memory}"]
    return cmd
