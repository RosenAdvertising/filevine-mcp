"""The setup wizard prints the same Claude Desktop config the README shows."""

from __future__ import annotations

import re
from pathlib import Path

from filevine_mcp import credentials
from filevine_mcp.setup import oauth_flow

README = Path(__file__).resolve().parent.parent / "README.md"


def _readme_claude_desktop_json() -> str:
    text = README.read_text(encoding="utf-8")
    section = text.split("## Usage with Claude Desktop", 1)[1]
    match = re.search(r"```json\n(.*?)\n```", section, re.DOTALL)
    assert match is not None
    return match.group(1)


def _run_setup(monkeypatch, tmp_path, capsys) -> str:
    answers = iter(["us", "synthetic-id", "synthetic-secret", "synthetic-pat", ""])
    monkeypatch.setattr(oauth_flow, "prompt", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        oauth_flow, "fetch_token", lambda *args, **kwargs: {"expires_in": 3600}
    )
    monkeypatch.setattr(credentials, "set_secret", lambda key, value: "keyring")
    monkeypatch.setattr(credentials, "storage_backend", lambda: "TestKeyring")
    monkeypatch.setattr(oauth_flow, "CONFIG_DIR", tmp_path / "filevine-config")
    oauth_flow._main()
    return capsys.readouterr().out


def test_setup_prints_the_readme_claude_desktop_config(
    monkeypatch, tmp_path, capsys
) -> None:
    output = _run_setup(monkeypatch, tmp_path, capsys)

    assert _readme_claude_desktop_json() in output
    assert oauth_flow.CLAUDE_DESKTOP_CONFIG == _readme_claude_desktop_json()
    assert '"command": "uv"' in output
    assert '"--directory", "/absolute/path/to/filevine-mcp", "filevine-mcp"' in output
    assert (
        "Replace /absolute/path/to/filevine-mcp with the path of your clone" in output
    )
    # The old snippet was a bare command that the README does not show.
    assert '"command": "filevine-mcp"' not in output
