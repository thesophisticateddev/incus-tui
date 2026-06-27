"""Thin wrapper around the `incus` CLI used by the TUI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field


class IncusError(Exception):
    """Raised when an `incus` command fails or is unavailable."""


class IncusUnavailable(IncusError):
    """Raised when the incus daemon is not reachable."""


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


# ---------------------------------------------------------------------------
# Daemon status / info
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DaemonStatus:
    reachable: bool
    server_version: str | None = None
    client_version: str | None = None
    address: str | None = None
    clustered: bool = False
    storage_backends: list[str] = field(default_factory=list)
    message: str | None = None

    @property
    def version_skew(self) -> bool:
        if not self.reachable or not self.server_version or not self.client_version:
            return False
        return self.server_version != self.client_version


def client_version() -> str:
    """Return the incus client version string."""
    result = subprocess.run(
        [_incus_path(), "version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise IncusError(result.stderr.strip() or "incus version failed")
    return result.stdout.strip()


def daemon_status() -> DaemonStatus:
    """Probe the incus daemon and return its status.

    Raises IncusUnavailable if the daemon socket cannot be reached.
    """
    path = shutil.which("incus")
    if path is None:
        return DaemonStatus(
            reachable=False,
            message="`incus` binary not found on PATH.",
        )

    result = subprocess.run(
        [_incus_path(), "info", "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "connection refused" in stderr.lower() or "socket" in stderr.lower():
            return DaemonStatus(
                reachable=False,
                message="Daemon not reachable. Is the incus daemon running?",
            )
        return DaemonStatus(
            reachable=False,
            message=stderr or "incus info failed",
        )

    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return DaemonStatus(reachable=False, message="Could not parse daemon response.")

    backends: list[str] = []
    for pool in data.get("storage", []):
        if isinstance(pool, dict):
            backends.append(pool.get("driver", "?"))

    return DaemonStatus(
        reachable=True,
        server_version=data.get("server_version"),
        client_version=data.get("client_version"),
        address=data.get("cluster_address") or data.get("server_address"),
        clustered=data.get("clustered", False),
        storage_backends=backends,
    )


def daemon_status_from_query() -> DaemonStatus:
    """Alternative probe using the REST API via incus query.

    Slightly cheaper; used by screens that already talk to the API.
    """
    result = subprocess.run(
        [_incus_path(), "query", "--format", "json", "/1.0"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return DaemonStatus(
            reachable=False,
            message="Daemon not reachable via API.",
        )
    return DaemonStatus(reachable=True)


# ---------------------------------------------------------------------------
# Server config
# ---------------------------------------------------------------------------


def server_info_command() -> list[str]:
    """Command to show server info (extended)."""
    return [_incus_path(), "info", "--format", "json"]


def server_info_raw_command() -> list[str]:
    """Command to show server info as plain text."""
    return [_incus_path(), "info"]


def server_config_show_command() -> list[str]:
    """Command to show server configuration as YAML."""
    return [_incus_path(), "config", "show"]


def server_config_get_command(key: str) -> list[str]:
    """Command to get a single server config key."""
    return [_incus_path(), "config", "get", key]


def server_config_set_command(key: str, value: str) -> list[str]:
    """Command to set a single server config key."""
    return [_incus_path(), "config", "set", key, value]


def server_config_edit_command() -> list[str]:
    """Command to edit full server config in $EDITOR."""
    return [_incus_path(), "config", "edit"]


# ---------------------------------------------------------------------------
# Trust / certificates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrustedClient:
    fingerprint: str
    type: str
    name: str
    certificate: str
    pid: int
    connection: str
    expiry: str | None = None


def trust_list_command() -> list[str]:
    """Command to list trusted certificates."""
    return [_incus_path(), "config", "trust", "list", "--format", "json"]


def trust_add_command(name: str, certificate: str) -> list[str]:
    """Command to add a trusted certificate."""
    return [_incus_path(), "config", "trust", "add", "--name", name, certificate]


def trust_remove_command(fingerprint: str) -> list[str]:
    """Command to remove a trusted certificate by fingerprint."""
    return [_incus_path(), "config", "trust", "remove", fingerprint]


def trust_list_tokens_command() -> list[str]:
    """Command to list active join tokens."""
    return [_incus_path(), "config", "trust", "list-tokens", "--format", "json"]


def trust_revoke_token_command(token_id: str) -> list[str]:
    """Command to revoke a join token by its ID."""
    return [_incus_path(), "config", "trust", "revoke-token", token_id]


def trust_add_token_command(
    name: str,
    *,
    expiry: str | None = None,
    projects: list[str] | None = None,
) -> list[str]:
    """Command to create a join token for a client to connect."""
    cmd = [_incus_path(), "config", "trust", "add-token", "--name", name]
    if expiry:
        cmd += ["--expiry", expiry]
    if projects:
        for p in projects:
            cmd += ["--project", p]
    return cmd


# ---------------------------------------------------------------------------
# Admin init
# ---------------------------------------------------------------------------


def admin_init_dump_command() -> list[str]:
    """Print current daemon configuration as YAML (for preseed)."""
    return [_incus_path(), "admin", "init", "--dump"]


def admin_init_minimal_command() -> list[str]:
    """One-shot minimal daemon initialisation."""
    return [_incus_path(), "admin", "init", "--minimal"]


def admin_init_auto_command(
    *,
    network_address: str | None = None,
    network_port: int | None = None,
    storage_backend: str | None = None,
    storage_pool: str | None = None,
    storage_loop_size: int | None = None,
) -> list[str]:
    """Build an ``incus admin init --auto`` command with the given options."""
    cmd = [_incus_path(), "admin", "init", "--auto"]
    if network_address:
        cmd += ["--network-address", network_address]
    if network_port:
        cmd += ["--network-port", str(network_port)]
    if storage_backend:
        cmd += ["--storage-backend", storage_backend]
    if storage_pool:
        cmd += ["--storage-pool", storage_pool]
    if storage_loop_size:
        cmd += ["--storage-create-loop", str(storage_loop_size)]
    return cmd


def admin_init_interactive_command() -> list[str]:
    """Run the full interactive daemon setup."""
    return [_incus_path(), "admin", "init"]


# ---------------------------------------------------------------------------
# Admin waitready / shutdown
# ---------------------------------------------------------------------------


def admin_waitready_command(timeout: int = 0) -> list[str]:
    """Command to block until the daemon is ready."""
    cmd = [_incus_path(), "admin", "waitready"]
    if timeout:
        cmd += ["-t", str(timeout)]
    return cmd


def admin_shutdown_command(*, force: bool = False, timeout: int = 60) -> list[str]:
    """Command to gracefully shut down all instances and stop the daemon."""
    cmd = [_incus_path(), "admin", "shutdown"]
    if force:
        cmd.append("-f")
    cmd += ["-t", str(timeout)]
    return cmd


# ---------------------------------------------------------------------------
# OS service lifecycle (POSIX-only)
# ---------------------------------------------------------------------------


class ServiceError(Exception):
    """Raised when service control is not available on the current platform."""


def _detect_init_system() -> str:
    """Detect the init system: 'systemd', 'launchd', or 'none'."""
    if os.path.exists("/run/systemd/system"):
        return "systemd"
    if os.path.exists("/var/run/com.apple.launchd.plist"):
        return "launchd"
    return "none"


def service_status_command(service: str = "incus") -> list[str]:
    """Return the command to check daemon/service status."""
    init = _detect_init_system()
    if init == "systemd":
        return ["systemctl", "is-active", f"{service}.service"]
    if init == "launchd":
        return ["launchctl", "print", f"gui/{os.getuid()}/incus"]
    raise ServiceError(
        f"Service control not supported on this platform. "
        "Daemon lifecycle requires systemd (Linux) or launchd (macOS)."
    )


def service_start_command(service: str = "incus") -> list[str]:
    """Return the command to start the incus daemon/service."""
    init = _detect_init_system()
    if init == "systemd":
        return ["systemctl", "start", f"{service}.service"]
    if init == "launchd":
        return ["launchctl", "boot", "system", f"incus"]
    raise ServiceError("Service control not supported on this platform.")


def service_stop_command(service: str = "incus") -> list[str]:
    """Return the command to stop the incus daemon/service."""
    init = _detect_init_system()
    if init == "systemd":
        return ["systemctl", "stop", f"{service}.service"]
    if init == "launchd":
        return ["launchctl", "boot", "out", "system", f"incus"]
    raise ServiceError("Service control not supported on this platform.")


def service_restart_command(service: str = "incus") -> list[str]:
    """Return the command to restart the incus daemon/service."""
    init = _detect_init_system()
    if init == "systemd":
        return ["systemctl", "restart", f"{service}.service"]
    if init == "launchd":
        return ["launchctl", "boot", "system", f"incus"]
    raise ServiceError("Service control not supported on this platform.")


def service_enable_command(service: str = "incus") -> list[str]:
    """Return the command to enable the incus daemon at boot."""
    init = _detect_init_system()
    if init == "systemd":
        return ["systemctl", "enable", f"{service}.service"]
    if init == "launchd":
        return ["launchctl", "boot", "onestart", "system", f"incus"]
    raise ServiceError("Service control not supported on this platform.")


def service_disable_command(service: str = "incus") -> list[str]:
    """Return the command to disable the incus daemon at boot."""
    init = _detect_init_system()
    if init == "systemd":
        return ["systemctl", "disable", f"{service}.service"]
    if init == "launchd":
        return ["launchctl", "boot", "offestart", "system", f"incus"]
    raise ServiceError("Service control not supported on this platform.")
