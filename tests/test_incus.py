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
