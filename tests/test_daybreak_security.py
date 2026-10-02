"""Daybreak review probes at the registered MCP or real setup/storage boundary."""

import asyncio
import json
import os
import stat
from unittest.mock import Mock

import pytest
from mcp.types import CallToolRequestParams

from filevine_mcp import client, credentials, server


def invoke(name, arguments):
    return asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name=name, arguments=arguments)
        )
    )


def text(result):
    return " ".join(part.text for part in result.content if hasattr(part, "text"))


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", [None, "chmod", "fchmod", "replace"])
def test_setup_secret_file_is_private_and_atomic(
    monkeypatch, tmp_path, existing, failure
):
    target = tmp_path / ".env"
    if existing:
        target.write_text("PROBE=old\n")
        target.chmod(0o644)
    monkeypatch.setattr(credentials, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(credentials, "ENV_FILE", target)
    monkeypatch.setattr(credentials, "_keyring_enabled", lambda: False)

    def save():
        credentials.set_secret("PROBE", "synthetic-value")

    original_open = os.open
    original_replace = os.replace
    seen_modes = []

    def checked_open(path, flags, mode=0o777, *args, **kwargs):
        fd = original_open(path, flags, mode, *args, **kwargs)
        if str(path).endswith(".tmp"):
            seen_modes.append(stat.S_IMODE(os.fstat(fd).st_mode))
            assert mode == 0o600
            assert os.fstat(fd).st_size == 0
        return fd

    def fail(*args, **kwargs):
        raise PermissionError("simulated permission failure")

    def checked_replace(source, dest):
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        assert "synthetic-value" in source.read_text()
        assert target.read_text() == "PROBE=old\n" if existing else not target.exists()
        return original_replace(source, dest)

    monkeypatch.setattr(os, "open", checked_open)
    monkeypatch.setattr(os, "replace", checked_replace)
    if failure == "chmod":
        monkeypatch.setattr(os, "chmod", fail)
    elif failure == "fchmod":
        monkeypatch.setattr(os, "fchmod", fail)
    elif failure == "replace":
        monkeypatch.setattr(os, "replace", fail)
    previous = os.umask(0o022)
    try:
        if failure in {"fchmod", "replace"}:
            with pytest.raises(PermissionError):
                save()
            assert (
                target.read_text() == "PROBE=old\n" if existing else not target.exists()
            )
        else:
            save()
            assert stat.S_IMODE(target.stat().st_mode) == 0o600
            assert "synthetic-value" in target.read_text()
    finally:
        os.umask(previous)
    assert seen_modes == [0o600]
    assert not list(tmp_path.glob(".*.tmp"))


BAD_URLS = [
    "http://example.com/",
    "file:///tmp/probe",
    "https://user:pass@example.com/",
    "https://127.0.0.1/",
    "https://2130706433/",
    "https://0x7f000001/",
    "https://017700000001/",
    "https://127.1/",
    "https://0177.0.0.1/",
    "https://0x7f.0.0.1/",
    "https://127.0.1/",
    "https://127.0.0.1./",
    "https://%31%32%37.0.0.1/",
    "https://[::1]/",
    "https://[::ffff:127.0.0.1]/",
    "https://[::ffff:7f00:1]/",
    "https://[fe80::1%25en0]/",
    "https://localhost/",
    "https://localhost.localdomain/",
    "https://foo.localhost.localdomain/",
    "https://foo.localhost./",
    "https://LOCALHOST./",
    "https://metadata.google.internal/",
    "https://10.0.0.1/",
    "https://169.254.169.254/",
    "https://100.64.0.1/",
    "https://192.0.2.1/",
    "https://224.0.0.1/",
    "https://240.0.0.1/",
    "https://[2001:db8::1]/",
    "https://[ff02::1]/",
    "https://example.com\\@127.1/",
    "https://example.com:bad/",
    "https://example.com\n/",
    "https://１２７.０.０.１/",
]


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv(
        "FILEVINE_ALLOWED_DESTINATION_HOSTS",
        ".example.com,8.8.8.8,2606:4700:4700::1111",
    )
    instance = object.__new__(client.FileVineClient)
    instance.post = Mock(return_value={"ok": True})
    instance.put = Mock(return_value={"ok": True})
    monkeypatch.setattr(server, "FileVineClient", lambda: instance)
    return instance


@pytest.mark.parametrize("url", BAD_URLS)
@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
def test_url_probe_rejected_at_mcp(api, name, args, key, url):
    arguments = dict(args)
    arguments[key] = url
    result = invoke(name, arguments)
    assert result.is_error, text(result)
    api.post.assert_not_called()
    api.put.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://hooks.example.com/event",
        "https://8.8.8.8/event",
        "https://[2606:4700:4700::1111]/event",
    ],
)
@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
def test_public_destination_reaches_transport(api, name, args, key, url):
    arguments = dict(args)
    arguments[key] = url
    result = invoke(name, arguments)
    assert not result.is_error, text(result)
    assert api.post.called or api.put.called
    assert url in str(api.post.call_args_list + api.put.call_args_list)


@pytest.mark.parametrize(
    "name,args",
    [
        (
            "create_webhook_subscription",
            {"event_name": "probe", "target_url": "https://example.com"},
        ),
        ("update_webhook_subscription", {"subscription_id": "probe"}),
        (
            "update_webhook_subscription",
            {"subscription_id": "probe", "target_url": "https://example.com"},
        ),
    ],
)
@pytest.mark.parametrize(
    "fields",
    [
        {"targetUrl": "http://127.0.0.1:8000"},
        {"target_url": "https://2130706433"},
        {"url": "https://0x7f000001"},
        {"nested": [{"targetUrl": "http://127.1"}]},
        {"targetUrl": "https://unlisted.invalid"},
    ],
)
def test_fields_json_cannot_override_destination(api, name, args, fields):
    result = invoke(name, {**args, "fields_json": json.dumps(fields)})
    assert result.is_error
    api.post.assert_not_called()
    api.put.assert_not_called()


def test_non_url_fields_preserved(api):
    result = invoke(
        "create_webhook_subscription",
        {
            "event_name": "probe",
            "target_url": "https://example.com",
            "fields_json": '{"active": true}',
        },
    )
    assert not result.is_error
    assert api.post.call_args.args[1]["active"] is True


@pytest.mark.parametrize("region", ["TYPO", "", "ca-"])
def test_invalid_config_region_fails_before_network(monkeypatch, region):
    import subprocess
    import sys

    env = dict(os.environ, FILEVINE_REGION=region)
    probe = subprocess.run(
        [sys.executable, "-c", "import filevine_mcp.client"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert probe.returncode != 0
    assert "Unsupported region" in probe.stderr


def test_setup_rejects_region_typo(monkeypatch, capsys):
    from filevine_mcp.setup import oauth_flow

    post = Mock(side_effect=AssertionError("no token exchange"))
    monkeypatch.setattr(oauth_flow.requests, "post", post)
    answers = iter(["ca-", "synthetic-id", "synthetic-secret", "synthetic-pat", ""])
    monkeypatch.setattr(oauth_flow, "prompt", lambda *a, **kw: next(answers))
    with pytest.raises(SystemExit) as caught:
        oauth_flow._main()
    assert caught.value.code == 1
    assert "Unsupported region" in capsys.readouterr().out
    post.assert_not_called()
