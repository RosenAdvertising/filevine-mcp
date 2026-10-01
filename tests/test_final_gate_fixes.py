"""HTTP failure and console entrypoint regression tests using fakes."""

import asyncio
from pathlib import Path
from typing import Any, cast

import pytest
import requests
from mcp_types import CallToolRequestParams, ReadResourceRequestParams

from filevine_mcp import client, server
from filevine_mcp.setup import oauth_flow, verify


class Response:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self.ok = 200 <= status < 400
        self._body = body
        self.headers = headers or {}
        self.content = b"" if body is None else b"present"

    def json(self):
        return self._body


class Session:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


def make_client(session) -> Any:
    instance = cast(Any, client.FileVineClient.__new__(client.FileVineClient))
    instance.tm = type(
        "Tokens",
        (),
        {
            "is_expired": lambda self: False,
            "fetch": lambda self: None,
            "get_valid_token": lambda self: "fake-token",
        },
    )()
    instance.session = session
    return instance


@pytest.mark.parametrize("status", [301, 302, 307, 400, 401, 403, 404, 429, 500, 503])
def test_empty_failure_responses_do_not_succeed(status, monkeypatch):
    monkeypatch.setattr(client.time, "sleep", lambda _seconds: None)
    responses = [Response(status)]
    if status == 401:
        responses.append(Response(status))
    elif status == 429:
        responses.extend(Response(status) for _ in range(3))
    api = make_client(Session(responses))
    with pytest.raises(client.FilevineClientError):
        api.post("projects")


def test_403_has_exact_access_guidance():
    api = make_client(Session([Response(403)]))
    with pytest.raises(client.FilevineClientError) as err:
        api.get("Users/Me")
    assert str(err.value) == (
        "Filevine access denied: the connected account lacks permission for this action "
        "(or the authorization expired; re-run filevine-mcp-setup if so)."
    )


def test_401_has_reauthorization_guidance():
    api = make_client(Session([Response(401), Response(401)]))
    with pytest.raises(client.FilevineClientError, match="Re-run filevine-mcp-setup"):
        api.get("Users/Me")


@pytest.mark.parametrize(
    ("method", "message"),
    [
        ("GET", "Check connectivity and retry."),
        ("POST", "the outcome is unknown. Check whether it completed before retrying."),
    ],
)
@pytest.mark.parametrize("failure", [requests.Timeout(), requests.ConnectionError()])
def test_connection_failures_are_safe_and_write_aware(method, message, failure):
    api = make_client(Session([failure]))
    with pytest.raises(client.FilevineClientError) as err:
        api._request(method, "projects")
    assert message in str(err.value)
    assert "sentinel" not in str(err.value)
    assert api.session.calls[0][2]["timeout"] == 30


def test_path_values_are_validated_as_single_segments():
    api = make_client(Session([Response(body={})]))
    api.get_user("normal-id")
    url = api.session.calls[0][1]
    assert url.endswith("users/normal-id")
    assert "../" not in url


def test_retry_after_budget_is_aggregate_and_preserves_vendor_delay(monkeypatch):
    waits = []
    monkeypatch.setattr(client.time, "sleep", waits.append)
    api = make_client(
        Session(
            [
                Response(429, headers={"Retry-After": "40"}),
                Response(429, headers={"Retry-After": "30"}),
            ]
        )
    )
    with pytest.raises(client.FilevineClientError, match="Retry after 30 seconds"):
        api.get("Users/Me")
    assert waits == [40]
    assert sum(waits) <= client.MAX_RETRY_SLEEP


def test_retry_after_budget_survives_unauthorized_refresh(monkeypatch):
    waits = []
    monkeypatch.setattr(client.time, "sleep", waits.append)
    api = make_client(
        Session(
            [
                Response(429, headers={"Retry-After": "40"}),
                Response(401),
                Response(429, headers={"Retry-After": "30"}),
            ]
        )
    )
    with pytest.raises(client.FilevineClientError, match="Retry after 30 seconds"):
        api.get("Users/Me")
    assert waits == [40]


def test_retry_after_limit_spans_repeated_tool_calls(monkeypatch):
    waits = []
    monkeypatch.setattr(client.time, "sleep", waits.append)
    api = make_client(
        Session(
            [
                Response(429, headers={"Retry-After": "40"}),
                Response(429, headers={"Retry-After": "15"}),
                Response(200, body={"ok": True}),
            ]
        )
    )
    assert api.get("Users/Me") == {"ok": True}
    assert waits == [40, 15]
    assert sum(waits) <= client.MAX_RETRY_SLEEP


def test_every_api_call_has_timeout_and_token_refresh_has_timeout(
    monkeypatch, tmp_path
):
    api = make_client(Session([Response(body={})]))
    api.get("Users/Me")
    assert api.session.calls[0][2]["timeout"] == client.REQUEST_TIMEOUT

    monkeypatch.setattr(client, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(client, "CLIENT_ID", "id")
    monkeypatch.setattr(client, "CLIENT_SECRET", "secret")
    monkeypatch.setattr(client, "FILEVINE_PAT", "pat")

    class TokenResponse(Response):
        status_code = 200

    captured = {}

    def post(url, **kwargs):
        captured.update(kwargs)
        return TokenResponse(body={"access_token": "fake", "expires_in": 10})

    monkeypatch.setattr(client.requests, "post", post)
    client.TokenManager().fetch()
    assert captured["timeout"] == client.REQUEST_TIMEOUT
    assert Path(tmp_path, "tokens.json").stat().st_mode & 0o777 == 0o600

    captured.clear()
    monkeypatch.setattr(oauth_flow.requests, "post", post)
    oauth_flow.fetch_token(
        "fake-id", "fake-secret", "https://identity.invalid", "fake-pat"
    )
    assert captured["timeout"] == oauth_flow.REQUEST_TIMEOUT


@pytest.mark.parametrize("status", [400, 401, 403, 500])
def test_tool_errors_return_is_error_without_vendor_text(monkeypatch, status):
    responses = [Response(status, body={"error": "vendor-sentinel"})]
    if status == 401:
        responses.append(Response(status, body={"error": "vendor-sentinel"}))
    api = make_client(Session(responses))
    monkeypatch.setattr(server, "FileVineClient", lambda: api)
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})
        )
    )
    assert result.is_error is True
    rendered = " ".join(part.text for part in result.content if hasattr(part, "text"))
    if status == 400:
        expected = (
            "Error executing tool get_current_user: Filevine request failed with HTTP 400. "
            "Check account permissions and request details."
        )
    elif status == 401:
        expected = (
            "Error executing tool get_current_user: Filevine authorization failed (401). "
            "Re-run filevine-mcp-setup to reauthorize."
        )
    elif status == 403:
        expected = (
            "Error executing tool get_current_user: Filevine access denied: the connected account "
            "lacks permission for this action (or the authorization expired; re-run "
            "filevine-mcp-setup if so)."
        )
    else:
        expected = (
            "Error executing tool get_current_user: Filevine request failed with HTTP 500. "
            "Check account permissions and request details."
        )
    assert rendered == expected
    assert "vendor-sentinel" not in rendered


@pytest.mark.parametrize(
    ("method", "failure", "expected"),
    [
        (
            "get_current_user",
            requests.Timeout(),
            "Error executing tool get_current_user: Filevine request timed out or lost its connection. Check connectivity and retry.",
        ),
        (
            "create_project",
            requests.ConnectionError("connection-sentinel"),
            "Error executing tool create_project: Filevine request timed out or lost its connection; the outcome is unknown. Check whether it completed before retrying.",
        ),
    ],
)
def test_timeout_and_connection_errors_are_is_error_and_write_aware(
    monkeypatch, method, failure, expected
):
    api = make_client(Session([failure]))
    monkeypatch.setattr(server, "FileVineClient", lambda: api)
    args = {"fields_json": "{}"} if method == "create_project" else {}
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name=method, arguments=args)
        )
    )
    assert result.is_error is True
    rendered = " ".join(part.text for part in result.content if hasattr(part, "text"))
    assert rendered == expected
    assert "connection-sentinel" not in rendered


def test_unexpected_tool_failure_is_masked(monkeypatch):
    def fail():
        raise RuntimeError("unknown-sentinel https://bad.example/token-secret")

    monkeypatch.setattr(server, "_c", fail)
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})
        )
    )
    assert result.is_error is True
    rendered = " ".join(part.text for part in result.content if hasattr(part, "text"))
    assert rendered.endswith(
        "Filevine request failed unexpectedly. Check configuration and try again."
    )
    assert "unknown-sentinel" not in rendered
    assert "bad.example" not in rendered


def test_missing_configuration_returns_exact_tool_error(monkeypatch):
    monkeypatch.setattr(client, "ORG_ID", "")
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})
        )
    )
    assert result.is_error is True
    rendered = " ".join(part.text for part in result.content if hasattr(part, "text"))
    assert rendered == (
        "Error executing tool get_current_user: FILEVINE_ORG_ID is required. "
        "Run filevine-mcp-setup."
    )


def test_confirmation_refusal_returns_is_error():
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None,
            CallToolRequestParams(
                name="delete_task", arguments={"task_id": "task-1", "confirm": False}
            ),
        )
    )
    assert result.is_error is True
    rendered = " ".join(part.text for part in result.content if hasattr(part, "text"))
    assert "confirm=True" in rendered


def test_resource_failure_is_safe_resource_error(monkeypatch):
    def fail():
        raise RuntimeError("resource-sentinel")

    monkeypatch.setattr(server, "_c", fail)
    with pytest.raises(Exception) as err:
        asyncio.run(
            server.mcp._handle_read_resource(
                None, ReadResourceRequestParams(uri="filevine://project_types")
            )
        )
    assert "resource-sentinel" not in str(err.value)
    assert str(err.value) == (
        "Filevine resource could not be read. Check configuration and try again."
    )


def test_verify_entrypoint_missing_credentials_exits_actionably(monkeypatch, capsys):
    def no_credentials():
        raise client.FilevineClientError(
            "FILEVINE_ORG_ID is required. Run filevine-mcp-setup."
        )

    monkeypatch.setattr(verify, "FileVineClient", no_credentials)
    with pytest.raises(SystemExit) as exit_error:
        verify.main()
    output = capsys.readouterr().out
    assert exit_error.value.code == 1
    assert "FILEVINE_ORG_ID is required" in output
    assert "filevine-mcp-setup" in output
    assert "Traceback" not in output


def test_setup_entrypoint_bad_key_exits_without_traceback(monkeypatch, capsys):
    answers = iter(["us", "fake-id", "fake-secret", "fake-pat", "fake-org"])
    monkeypatch.setattr(oauth_flow, "prompt", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        oauth_flow.requests, "post", lambda *args, **kwargs: Response(401)
    )
    with pytest.raises(SystemExit) as exit_error:
        oauth_flow.main()
    output = capsys.readouterr().out
    assert exit_error.value.code == 1
    assert "Check the client ID, secret, and PAT" in output
    assert "Traceback" not in output


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"access_token": "", "expires_in": 10},
        {"access_token": "fake", "expires_in": "soon"},
    ],
)
def test_setup_malformed_success_envelope_exits_without_traceback(
    monkeypatch, capsys, body
):
    answers = iter(["us", "fake-id", "fake-secret", "fake-pat", "fake-org"])
    monkeypatch.setattr(oauth_flow, "prompt", lambda *args, **kwargs: next(answers))
    monkeypatch.setattr(
        oauth_flow.requests, "post", lambda *args, **kwargs: Response(body=body)
    )
    with pytest.raises(SystemExit) as exit_error:
        oauth_flow.main()
    output = capsys.readouterr().out
    assert exit_error.value.code == 1
    assert "invalid authorization response" in output
    assert "Traceback" not in output


def test_setup_entrypoint_eof_fails_clearly(monkeypatch, capsys):
    monkeypatch.setattr(
        oauth_flow, "prompt", lambda *args, **kwargs: (_ for _ in ()).throw(EOFError)
    )
    with pytest.raises(SystemExit) as exit_error:
        oauth_flow.main()
    output = capsys.readouterr().out
    assert exit_error.value.code == 1
    assert "input ended early" in output
    assert "Traceback" not in output


def test_setup_entrypoint_empty_required_inputs_fails_clearly(monkeypatch, capsys):
    answers = iter(["us", "", "fake-secret", "fake-pat", "fake-org"])
    monkeypatch.setattr(oauth_flow, "prompt", lambda *args, **kwargs: next(answers))
    with pytest.raises(SystemExit) as exit_error:
        oauth_flow.main()
    output = capsys.readouterr().out
    assert exit_error.value.code == 1
    assert "Client ID, Client Secret, and PAT are required" in output
    assert "Testing credentials" not in output
    assert "Traceback" not in output


def test_validation_hides_rejected_values():
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None,
            CallToolRequestParams(
                name="list_projects", arguments={"limit": "PRIVATE_VALUE"}
            ),
        )
    )
    assert result.is_error is True
    assert (
        result.content[0].text
        == "Invalid argument 'limit'; expected integer greater than or equal to 1 and less than or equal to 200."
    )


@pytest.mark.parametrize(
    "error_type", [RuntimeError, ValueError, server.ToolError, server.ResourceError]
)
def test_arbitrary_exception_types_cannot_expose_private_text(monkeypatch, error_type):
    def fail():
        raise error_type("PRIVATE_VALUE")

    monkeypatch.setattr(server, "_c", fail)
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})
        )
    )
    assert result.is_error is True
    expected = (
        "Invalid tool arguments. Check the supplied values."
        if error_type is ValueError
        else "Filevine request failed unexpectedly. Check configuration and try again."
    )
    assert (
        result.content[0].text == "Error executing tool get_current_user: " + expected
    )


def test_verify_masks_arbitrary_value_error(monkeypatch, capsys):
    monkeypatch.setattr(
        verify,
        "FileVineClient",
        lambda: (_ for _ in ()).throw(ValueError("PRIVATE_VALUE")),
    )
    with pytest.raises(SystemExit) as stopped:
        verify.main()
    assert stopped.value.code == 1
    assert capsys.readouterr().out == (
        "Verifying Filevine MCP credentials...\n"
        "✗ Verification failed. Check the organization ID and stored tokens; run filevine-mcp-setup.\n"
    )


def test_unreadable_success_response_is_a_tool_error(monkeypatch):
    class Unreadable(Response):
        def json(self):
            raise ValueError("PRIVATE_VALUE")

    api = make_client(Session([Unreadable(body="invalid")]))
    monkeypatch.setattr(server, "FileVineClient", lambda: api)
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})
        )
    )
    assert result.is_error is True
    assert (
        result.content[0].text
        == "Error executing tool get_current_user: Filevine returned an unreadable response."
    )


def test_long_retry_after_returns_hint_without_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(client.time, "sleep", sleeps.append)
    api = make_client(Session([Response(429, headers={"Retry-After": "61"})]))
    monkeypatch.setattr(server, "FileVineClient", lambda: api)
    result = asyncio.run(
        server.mcp._handle_call_tool(
            None, CallToolRequestParams(name="get_current_user", arguments={})
        )
    )
    assert result.is_error is True
    assert (
        result.content[0].text
        == "Error executing tool get_current_user: Filevine rate limit reached. Retry after 61 seconds."
    )
    assert sleeps == []


@pytest.mark.parametrize("header", ["60.1", "Thu, 01 Jan 1970 00:01:01 GMT"])
def test_fractional_and_date_retry_after_preserve_long_delay(monkeypatch, header):
    sleeps = []
    monkeypatch.setattr(client.time, "sleep", sleeps.append)
    monkeypatch.setattr(client.time, "time", lambda: 0)
    api = make_client(Session([Response(429, headers={"Retry-After": header})]))
    with pytest.raises(client.FilevineClientError, match="Retry after 61 seconds"):
        api.get("Users/Me")
    assert sleeps == []
