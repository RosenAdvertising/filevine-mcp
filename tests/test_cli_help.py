"""CLI help must not load credentials, touch files, or start a connection."""

import builtins
import getpass
import io
import os
from pathlib import Path
import socket
import subprocess
import sys

import keyring
import pytest

from filevine_mcp import cli


@pytest.mark.parametrize("command", ["setup", "verify"])
@pytest.mark.parametrize("args", [["--help"], ["-h"], ["--unused", "--help"]])
def test_help_without_io(command, args, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Help attempted an import, configuration, or I/O operation"
        )

    monkeypatch.setattr(sys, "argv", [f"filevine-mcp-{command}", *args])
    with monkeypatch.context() as guard:
        for owner, names in [
            (builtins, ["open", "input"]),
            (io, ["open"]),
            (os, ["open", "stat", "lstat", "listdir", "scandir"]),
            (Path, ["home", "open", "exists", "is_file", "is_dir", "mkdir"]),
            (
                keyring,
                ["get_password", "set_password", "delete_password", "get_keyring"],
            ),
            (socket, ["socket", "create_connection", "getaddrinfo"]),
            (getpass, ["getpass"]),
        ]:
            for name in names:
                guard.setattr(owner, name, forbidden)
        guard.setattr(builtins, "__import__", forbidden)
        assert getattr(cli, f"{command}_main")() is None
    output = capsys.readouterr()
    assert f"Usage: filevine-mcp-{command}" in output.out
    assert "-h, --help" in output.out
    assert not output.err


@pytest.mark.parametrize("command", ["setup", "verify"])
def test_missing_configuration_still_fails(command, tmp_path):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        "FILEVINE_MCP_USE_KEYRING": "0",
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
    }
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    code = (
        "import sys\n"
        "def offline(event, args):\n"
        "    if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:\n"
        "        raise AssertionError('No network allowed without configuration')\n"
        "sys.addaudithook(offline)\n"
        f"from filevine_mcp.cli import {command}_main\n"
        f"{command}_main()\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed Python command, isolated environment
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert "Usage:" not in result.stdout
    expected = {
        "setup": "Setup input ended early.",
        "verify": "Check the organization ID and stored tokens; run filevine-mcp-setup.",
    }
    assert expected[command] in result.stdout + result.stderr
