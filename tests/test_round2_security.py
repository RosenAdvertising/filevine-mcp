"""Round 2 policy regressions through registered MCP calls, with mocked transport."""

import pytest
from test_daybreak_security import api as api
from test_daybreak_security import invoke, text, BAD_URLS

SETTING = "FILEVINE_ALLOWED_DESTINATION_HOSTS"


@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
@pytest.mark.parametrize(
    "url",
    BAD_URLS
    + [
        "https://127.0.0.1.sslip.io/",
        "https://example.com/redirect?next=http%3A%2F%2F127.0.0.1%2F",
        "https://unlisted.example/",
        "https://hooks.firm.example.attacker.example/",
        "https://nothooks.firm.example/",
    ],
)
def test_unapproved_destination_zero_requests(api, monkeypatch, name, args, key, url):
    monkeypatch.setenv(SETTING, "hooks.firm.example")
    arguments = dict(args)
    arguments[key] = url
    result = invoke(name, arguments)
    assert result.is_error, text(result)
    api.post.assert_not_called()
    api.put.assert_not_called()


@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
@pytest.mark.parametrize("setting", [None, "", " , "])
def test_missing_allowlist_actionable_zero_requests(
    api, monkeypatch, name, args, key, setting
):
    if setting is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, setting)
    url = "https://hooks.firm.example/event"
    arguments = dict(args)
    arguments[key] = url
    result = invoke(name, arguments)
    assert result.is_error, text(result)
    assert SETTING in text(result)
    api.post.assert_not_called()
    api.put.assert_not_called()


@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
@pytest.mark.parametrize(
    "setting,url",
    [
        ("hooks.firm.example", "https://hooks.firm.example/event"),
        (
            " unrelated.example, HOOKS.FIRM.EXAMPLE. ",
            "https://HOOKS.FIRM.EXAMPLE./event",
        ),
        (".firm.example", "https://firm.example/event"),
        (".firm.example", "https://sub.hooks.firm.example/event"),
        ("bücher.example", "https://xn--bcher-kva.example/event"),
        ("xn--bcher-kva.example", "https://bücher.example/event"),
    ],
)
def test_approved_destination_preserved(
    api, monkeypatch, name, args, key, setting, url
):
    monkeypatch.setenv(SETTING, setting)
    arguments = dict(args)
    arguments[key] = url
    result = invoke(name, arguments)
    assert not result.is_error, text(result)
    assert api.post.called or api.put.called
    assert url in str(api.post.call_args_list + api.put.call_args_list)


@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
@pytest.mark.parametrize(
    "setting,url",
    [
        ("firm.example", "https://sub.firm.example/"),
        (".firm.example", "https://notfirm.example/"),
        (".firm.example", "https://firm.example.attacker.example/"),
        ("*", "https://hooks.firm.example/"),
        ("https://hooks.firm.example", "https://hooks.firm.example/"),
        ("hooks.firm.example/path", "https://hooks.firm.example/"),
        ("hooks.firm.example:443", "https://hooks.firm.example/"),
    ],
)
def test_allowlist_is_exact_and_fail_closed(
    api, monkeypatch, name, args, key, setting, url
):
    monkeypatch.setenv(SETTING, setting)
    arguments = dict(args)
    arguments[key] = url
    result = invoke(name, arguments)
    assert result.is_error, text(result)
    api.post.assert_not_called()
    api.put.assert_not_called()


@pytest.mark.parametrize(
    "name,args,key",
    [
        ("create_webhook_subscription", {"event_name": "probe"}, "target_url"),
        ("update_webhook_subscription", {"subscription_id": "probe"}, "target_url"),
    ],
)
@pytest.mark.parametrize(
    "setting,url",
    [
        (None, "https://hooks.firm.example/"),
        ("hooks.firm.example", "https://127.0.0.1.sslip.io/"),
        (
            "hooks.firm.example",
            "https://example.com/redirect?next=http%3A%2F%2F127.0.0.1%2F",
        ),
    ],
)
def test_rejection_precedes_client_construction(
    monkeypatch, name, args, key, setting, url
):
    from unittest.mock import Mock
    from filevine_mcp import server

    factory = Mock(side_effect=AssertionError("no client or token refresh"))
    monkeypatch.setattr(server, "FileVineClient", factory)
    if setting is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, setting)
    arguments = dict(args)
    arguments[key] = url
    assert invoke(name, arguments).is_error
    factory.assert_not_called()


@pytest.mark.parametrize(
    "name,args",
    [
        (
            "create_webhook_subscription",
            {"event_name": "probe", "target_url": "https://hooks.firm.example/"},
        ),
        ("update_webhook_subscription", {"subscription_id": "probe"}),
    ],
)
@pytest.mark.parametrize(
    "key",
    [
        "targetUrl",
        "TARGET_URL",
        "target-uri",
        "url",
        "uri",
        "callbackUrl",
        "callback_uri",
        "baseUrlPattern",
        "BASE_URL",
        "webhookUrl",
        "destination_uri",
        "redirectUrl",
        "endpoint_uri",
        "uploadUrl",
        "storageUrl",
        "pluginUrl",
    ],
)
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://hooks.firm.example/callback", True),
        ("https://127.0.0.1.sslip.io/", False),
        ("https://example.com/redirect?next=http%3A%2F%2F127.0.0.1%2F", False),
        ("https://unlisted.example/", False),
        ("https://2130706433/", False),
        (None, False),
    ],
)
def test_fields_destination_aliases_at_mcp(
    api, monkeypatch, name, args, key, nested, url, allowed
):
    import json

    monkeypatch.setenv(SETTING, "hooks.firm.example")
    fields = {key: url}
    if nested:
        fields = {"metadata": [{"values": fields}]}
    result = invoke(name, {**args, "fields_json": json.dumps(fields)})
    assert result.is_error is (not allowed), text(result)
    if allowed:
        assert api.post.called or api.put.called
    else:
        api.post.assert_not_called()
        api.put.assert_not_called()


@pytest.mark.parametrize(
    "name,args",
    [
        (
            "create_webhook_subscription",
            {"event_name": "probe", "target_url": "https://hooks.firm.example/"},
        ),
        ("update_webhook_subscription", {"subscription_id": "probe"}),
    ],
)
def test_unrelated_fields_are_preserved(api, monkeypatch, name, args):
    import json

    monkeypatch.setenv(SETTING, "hooks.firm.example")
    fields = {
        "securityLevel": "strict",
        "jurisdiction": "US",
        "metadata": [{"securityLevel": "strict", "jurisdiction": "US"}],
    }
    result = invoke(name, {**args, "fields_json": json.dumps(fields)})
    assert not result.is_error, text(result)
    sent = (api.post if api.post.called else api.put).call_args.args[1]
    assert all(sent[key] == value for key, value in fields.items())


@pytest.mark.parametrize("region", ["US", " us ", "\tUS\n", "CA"])
def test_region_normalization_at_mcp(region):
    import os
    import subprocess
    import sys
    import textwrap

    code = textwrap.dedent("""
        import asyncio
        from unittest.mock import Mock
        from mcp.types import CallToolRequestParams
        from filevine_mcp import client, server
        assert client.REGION == EXPECTED
        assert client.BASE_URL == client.REGIONS[EXPECTED]["api"]
        response = Mock(status_code=200, headers={}, ok=True)
        response.json.return_value = {"ok": True}
        session = Mock()
        session.request.return_value = response
        client.requests.Session = lambda: session
        tm = Mock(access_token="synthetic-value", refresh_token="")
        tm.is_expired.return_value = False
        tm.get_valid_token.return_value = "synthetic-value"
        client.TokenManager = lambda: tm
        client.ORG_ID = "synthetic-org"
        client.API_KEY = "synthetic-key"
        result = asyncio.run(server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})))
        assert not result.is_error, result
        assert session.request.call_args.args[1].startswith(client.BASE_URL + "/")
    """)
    code = code.replace("EXPECTED", repr(region.strip().lower()))
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=dict(os.environ, FILEVINE_REGION=region),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("region", ["US", " ca ", " CJIS "])
def test_setup_normalizes_region(monkeypatch, tmp_path, region):
    from unittest.mock import Mock
    from filevine_mcp.setup import oauth_flow

    answers = iter([region, "synthetic-id", "synthetic-secret", "synthetic-pat", ""])
    monkeypatch.setattr(oauth_flow, "prompt", lambda *a, **kw: next(answers))
    token = Mock(return_value={"access_token": "synthetic-value", "expires_in": 3600})
    monkeypatch.setattr(oauth_flow, "fetch_token", token)
    save = Mock(return_value="file")
    monkeypatch.setattr(oauth_flow.credentials, "set_secret", save)
    monkeypatch.setattr(oauth_flow, "CONFIG_DIR", tmp_path)
    oauth_flow._main()
    normalized = region.strip().lower()
    assert token.call_args.args[2] == oauth_flow.REGIONS[normalized]["identity"]
    save.assert_any_call("FILEVINE_REGION", normalized)


@pytest.mark.parametrize(
    "url",
    BAD_URLS
    + [
        "https://127.0.0.1.sslip.io/",
        "https://example.com/redirect?next=http%3A%2F%2F127.0.0.1%2F",
    ],
)
def test_nested_json_rejection_precedes_client(monkeypatch, url):
    import json
    from unittest.mock import Mock
    from filevine_mcp import server

    monkeypatch.setenv(SETTING, "hooks.firm.example")
    factory = Mock(side_effect=AssertionError("no client or token refresh"))
    monkeypatch.setattr(server, "FileVineClient", factory)
    result = invoke(
        "update_webhook_subscription",
        {
            "subscription_id": "probe",
            "fields_json": json.dumps({"metadata": [{"CALLBACK_URL": url}]}),
        },
    )
    assert result.is_error
    factory.assert_not_called()


@pytest.mark.parametrize("setting", [None, "", " , "])
def test_json_destination_requires_allowlist(monkeypatch, setting):
    import json
    from unittest.mock import Mock
    from filevine_mcp import server

    if setting is None:
        monkeypatch.delenv(SETTING, raising=False)
    else:
        monkeypatch.setenv(SETTING, setting)
    factory = Mock(side_effect=AssertionError("no client or token refresh"))
    monkeypatch.setattr(server, "FileVineClient", factory)
    result = invoke(
        "update_webhook_subscription",
        {
            "subscription_id": "probe",
            "fields_json": json.dumps({"targetUrl": "https://hooks.firm.example/"}),
        },
    )
    assert result.is_error
    assert SETTING in text(result)
    factory.assert_not_called()
