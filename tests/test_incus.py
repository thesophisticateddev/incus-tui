"""Unit tests for the incus CLI wrapper (no real incus needed)."""

from types import SimpleNamespace

import pytest

from incus_tui.components import incus

_FAKE_LIST = """
[
  {
    "name": "web", "status": "Running", "type": "container",
    "state": {"network": {
      "eth0": {"addresses": [
        {"family": "inet", "address": "10.0.0.5", "scope": "global"},
        {"family": "inet6", "address": "fe80::1", "scope": "link"},
        {"family": "inet6", "address": "fd42::5", "scope": "global"}
      ]},
      "lo": {"addresses": [
        {"family": "inet", "address": "127.0.0.1", "scope": "local"}
      ]}
    }}
  },
  {"name": "db", "status": "Stopped", "type": "container", "state": null}
]
"""


def _fake_run(stdout="", returncode=0, stderr=""):
    return lambda *a, **k: SimpleNamespace(
        stdout=stdout, returncode=returncode, stderr=stderr
    )


def test_list_containers_parses_and_filters(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    monkeypatch.setattr(incus.subprocess, "run", _fake_run(stdout=_FAKE_LIST))

    containers = incus.list_containers()
    assert [c.name for c in containers] == ["db", "web"]  # sorted by name

    web = next(c for c in containers if c.name == "web")
    assert web.status == "Running" and web.is_running
    assert web.ipv4 == "10.0.0.5"  # global only; lo skipped
    assert web.ipv6 == "fd42::5"  # link-local excluded

    db = next(c for c in containers if c.name == "db")
    assert db.ipv4 == "" and not db.is_running


def test_list_containers_missing_binary(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: None)
    with pytest.raises(incus.IncusError):
        incus.list_containers()


def test_list_containers_command_failure(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    monkeypatch.setattr(
        incus.subprocess, "run", _fake_run(returncode=1, stderr="boom")
    )
    with pytest.raises(incus.IncusError, match="boom"):
        incus.list_containers()


def test_list_containers_bad_json(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    monkeypatch.setattr(incus.subprocess, "run", _fake_run(stdout="not json"))
    with pytest.raises(incus.IncusError):
        incus.list_containers()


def test_command_builders(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    assert incus.shell_command("foo") == ["/usr/bin/incus", "shell", "foo"]
    assert incus.mount_command("foo", "/tmp/x") == [
        "/usr/bin/incus",
        "file",
        "mount",
        "foo/",
        "/tmp/x",
    ]
    assert incus.ssh_command("root", "1.2.3.4") == ["ssh", "root@1.2.3.4"]
    assert incus.ssh_command("", "1.2.3.4") == ["ssh", "1.2.3.4"]


def test_launch_command(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    assert incus.launch_command("images:debian/12", "db") == [
        "/usr/bin/incus",
        "launch",
        "images:debian/12",
        "db",
    ]
    assert incus.launch_command(
        "images:ubuntu/24.04", "web", cpu="4", memory="2GiB", vm=True
    ) == [
        "/usr/bin/incus",
        "launch",
        "images:ubuntu/24.04",
        "web",
        "--vm",
        "-c",
        "limits.cpu=4",
        "-c",
        "limits.memory=2GiB",
    ]


def test_normalize_image():
    assert incus.normalize_image("ubuntu/24.04") == "images:ubuntu/24.04"
    assert incus.normalize_image("images:debian/12") == "images:debian/12"
    assert incus.normalize_image("local:my-image") == "local:my-image"


def test_validate_instance_name():
    assert incus.validate_instance_name("web-1") is None
    assert incus.validate_instance_name("") is not None
    assert incus.validate_instance_name("bad name") is not None
    assert incus.validate_instance_name("-lead") is not None
    assert incus.validate_instance_name("trail-") is not None
    assert incus.validate_instance_name("123") is not None
    assert incus.validate_instance_name("a" * 64) is not None


def test_validate_memory():
    for good in ("512MiB", "2GiB", "4GB", "1.5GiB"):
        assert incus.validate_memory(good) is None
    for bad in ("2", "lots", "2 GiB", "2Gigs"):
        assert incus.validate_memory(bad) is not None


# ---------------------------------------------------------------------------
# Daemon status
# ---------------------------------------------------------------------------

_FAKE_INFO = """
{
  "server_version": "6.0.0",
  "client_version": "6.0.0",
  "server_address": "0.0.0.0:8443",
  "clustered": false,
  "storage": [
    {"driver": "zfs", "pool": "default"}
  ]
}
"""


def test_daemon_status_reachable(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    monkeypatch.setattr(incus.subprocess, "run", _fake_run(stdout=_FAKE_INFO))

    status = incus.daemon_status()
    assert status.reachable
    assert status.server_version == "6.0.0"
    assert status.client_version == "6.0.0"
    assert status.clustered is False
    assert status.storage_backends == ["zfs"]
    assert status.version_skew is False


def test_daemon_status_unreachable_connection_refused(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    monkeypatch.setattr(
        incus.subprocess, "run",
        _fake_run(returncode=1, stderr="Error: Get \"unix:///var/lib/incus/unix.sock\": connection refused")
    )

    status = incus.daemon_status()
    assert not status.reachable
    assert "not reachable" in status.message


def test_daemon_status_binary_missing(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: None)
    status = incus.daemon_status()
    assert not status.reachable
    assert "not found" in status.message


def test_daemon_status_version_skew(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    skew_info = """
    {
      "server_version": "6.0.0",
      "client_version": "6.1.0",
      "server_address": "0.0.0.0:8443",
      "clustered": false,
      "storage": []
    }
    """
    monkeypatch.setattr(incus.subprocess, "run", _fake_run(stdout=skew_info))
    status = incus.daemon_status()
    assert status.reachable
    assert status.version_skew is True


# ---------------------------------------------------------------------------
# Command builders (daemon)
# ---------------------------------------------------------------------------

def test_server_config_commands(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    assert incus.server_config_show_command() == ["/usr/bin/incus", "config", "show"]
    assert incus.server_config_get_command("core.https_address") == [
        "/usr/bin/incus", "config", "get", "core.https_address"
    ]
    assert incus.server_config_set_command("core.debug", "true") == [
        "/usr/bin/incus", "config", "set", "core.debug", "true"
    ]
    assert incus.server_config_edit_command() == ["/usr/bin/incus", "config", "edit"]


def test_trust_commands(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    assert incus.trust_list_command() == [
        "/usr/bin/incus", "config", "trust", "list", "--format", "json"
    ]
    assert incus.trust_add_command("laptop", "/tmp/cert.crt") == [
        "/usr/bin/incus", "config", "trust", "add", "--name", "laptop", "/tmp/cert.crt"
    ]
    assert incus.trust_remove_command("fp123") == [
        "/usr/bin/incus", "config", "trust", "remove", "fp123"
    ]
    assert incus.trust_list_tokens_command() == [
        "/usr/bin/incus", "config", "trust", "list-tokens", "--format", "json"
    ]
    assert incus.trust_revoke_token_command("tok123") == [
        "/usr/bin/incus", "config", "trust", "revoke-token", "tok123"
    ]
    assert incus.trust_add_token_command("ci", expiry="24h", projects=["default"]) == [
        "/usr/bin/incus", "config", "trust", "add-token", "--name", "ci",
        "--expiry", "24h", "--project", "default"
    ]


def test_admin_init_commands(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    assert incus.admin_init_dump_command() == ["/usr/bin/incus", "admin", "init", "--dump"]
    assert incus.admin_init_minimal_command() == ["/usr/bin/incus", "admin", "init", "--minimal"]
    assert incus.admin_init_interactive_command() == ["/usr/bin/incus", "admin", "init"]
    assert incus.admin_init_auto_command() == ["/usr/bin/incus", "admin", "init", "--auto"]
    assert incus.admin_init_auto_command(
        network_address="0.0.0.0:8443",
        storage_backend="zfs",
        storage_loop_size=10,
    ) == [
        "/usr/bin/incus", "admin", "init", "--auto",
        "--network-address", "0.0.0.0:8443",
        "--storage-backend", "zfs",
        "--storage-create-loop", "10",
    ]


def test_admin_waitready_shutdown_commands(monkeypatch):
    monkeypatch.setattr(incus.shutil, "which", lambda _: "/usr/bin/incus")
    assert incus.admin_waitready_command() == ["/usr/bin/incus", "admin", "waitready"]
    assert incus.admin_waitready_command(timeout=30) == [
        "/usr/bin/incus", "admin", "waitready", "-t", "30"
    ]
    assert incus.admin_shutdown_command() == [
        "/usr/bin/incus", "admin", "shutdown", "-t", "60"
    ]
    assert incus.admin_shutdown_command(force=True, timeout=30) == [
        "/usr/bin/incus", "admin", "shutdown", "-f", "-t", "30"
    ]


def test_service_commands_systemd(monkeypatch):
    monkeypatch.setattr(incus.os.path, "exists", lambda p: p == "/run/systemd/system")
    assert incus.service_start_command() == ["systemctl", "start", "incus.service"]
    assert incus.service_stop_command() == ["systemctl", "stop", "incus.service"]
    assert incus.service_restart_command() == ["systemctl", "restart", "incus.service"]
    assert incus.service_enable_command() == ["systemctl", "enable", "incus.service"]
    assert incus.service_disable_command() == ["systemctl", "disable", "incus.service"]
    assert incus.service_status_command() == ["systemctl", "is-active", "incus.service"]


def test_service_commands_unsupported(monkeypatch):
    monkeypatch.setattr(incus.os.path, "exists", lambda p: False)
    for fn in (
        incus.service_start_command,
        incus.service_stop_command,
        incus.service_restart_command,
        incus.service_enable_command,
        incus.service_disable_command,
        incus.service_status_command,
    ):
        with pytest.raises(incus.ServiceError):
            fn()

