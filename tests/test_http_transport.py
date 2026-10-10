"""Offline integration tests for the stateless HTTP serving entry point."""

import asyncio
import json
from contextlib import asynccontextmanager
from importlib.metadata import version

import httpx
import pytest

from filevine_mcp import server
from test_final_gate_fixes import Response, Session, make_client
from test_spec_2026_07_28 import SERVER_INFO_META_KEY, _modern_request


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for key in (
        "FILEVINE_MCP_TRANSPORT",
        "FILEVINE_MCP_HOST",
        "FILEVINE_MCP_ALLOWED_HOSTS",
        "FILEVINE_MCP_ALLOWED_ORIGINS",
        "PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        server,
        "FileVineClient",
        lambda: pytest.fail("Unexpected vendor client construction"),
    )


@asynccontextmanager
async def http_client():
    app = server.create_serve_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1:8080",
        ) as client:
            yield client


async def post(client, method, params=None, *, request_id=1, headers=None):
    request_headers, body = _modern_request(method, params, request_id=request_id)
    request_headers["accept"] = "application/json, text/event-stream"
    request_headers.update(headers or {})
    return await client.post("/mcp", headers=request_headers, json=body)


def payload(response):
    assert response.status_code == 200, response.text
    if response.headers["content-type"].startswith("text/event-stream"):
        messages = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        return next(message for message in messages if "id" in message)
    return response.json()


def test_http_tools_match_stdio_names_and_input_schemas():
    async def check():
        stdio_tools = await server.mcp.list_tools()
        async with http_client() as client:
            response = await post(client, "tools/list")
        tools = payload(response)["result"]["tools"]
        assert [(tool["name"], tool["inputSchema"]) for tool in tools] == [
            (tool.name, tool.input_schema) for tool in stdio_tools
        ]
        assert len(tools) == 147
        assert "mcp-session-id" not in response.headers

    asyncio.run(check())


def test_http_read_tool_returns_normal_result_with_existing_vendor_mocks(monkeypatch):
    body = {"userId": "user-7", "name": "Offline User"}
    session = Session([Response(body=body)])
    api = make_client(session)
    monkeypatch.setattr(server, "FileVineClient", lambda: api)

    async def check():
        async with http_client() as client:
            response = await post(
                client,
                "tools/call",
                {"name": "get_current_user", "arguments": {}},
                headers={"authorization": "Bearer ignored-test-value"},
            )
        result = payload(response)["result"]
        assert result["isError"] is False
        assert result["content"][0]["text"] == json.dumps(body, indent=2)
        assert "mcp-session-id" not in response.headers
        assert len(session.calls) == 1
        method, url, kwargs = session.calls[0]
        assert method == "GET"
        assert url.endswith("/fv-app/v2/Users/Me")
        assert "ignored-test-value" not in str(kwargs)

    asyncio.run(check())


def test_concurrent_requests_have_separate_connections_and_one_lifespan(monkeypatch):
    lowlevel = server.mcp._lowlevel_server
    entry = lowlevel.get_request_handler("tools/list")
    connections = []
    lifecycle = []

    @asynccontextmanager
    async def lifespan(_server):
        lifecycle.append("start")
        yield {"marker": "app-lifespan"}
        lifecycle.append("stop")

    async def observed_list(ctx, params):
        connection = ctx.session._connection
        assert connection.session_id is None
        assert connection.state == {}
        connection.state["request_id"] = ctx.request_id
        connections.append(connection)
        assert ctx.lifespan_context == {"marker": "app-lifespan"}
        await asyncio.sleep(0)
        return await entry.handler(ctx, params)

    monkeypatch.setattr(lowlevel, "lifespan", lifespan)
    monkeypatch.setitem(
        lowlevel._request_handlers,
        "tools/list",
        type(entry)(entry.params_type, observed_list),
    )

    async def check():
        async with http_client() as client:
            first, second = await asyncio.gather(
                post(client, "tools/list", request_id=11),
                post(
                    client,
                    "tools/list",
                    request_id=22,
                    headers={"mcp-session-id": "unrecognized-session"},
                ),
            )
            assert payload(first)["id"] == 11
            assert payload(second)["id"] == 22
            assert payload(first)["result"] == payload(second)["result"]
            assert "mcp-session-id" not in first.headers
            assert "mcp-session-id" not in second.headers
            assert lifecycle == ["start"]
            assert connections[0] is not connections[1]
        assert lifecycle == ["start", "stop"]

    asyncio.run(check())


@pytest.mark.parametrize("transport", [None, " STDIO ", " "])
def test_default_transport_keeps_existing_stdio_call(monkeypatch, transport):
    if transport is not None:
        monkeypatch.setenv("FILEVINE_MCP_TRANSPORT", transport)
    calls = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **kw: calls.append((a, kw)))
    server.main()
    assert calls == [((), {})]


def test_http_transport_selection_is_normalized(monkeypatch):
    calls = []

    async def serve():
        calls.append("http")

    monkeypatch.setenv("FILEVINE_MCP_TRANSPORT", " STREAMABLE-HTTP ")
    monkeypatch.setattr(server, "_serve_streamable_http", serve)
    server.main()
    assert calls == ["http"]


def test_unknown_transport_exits_with_options(monkeypatch):
    monkeypatch.setenv("FILEVINE_MCP_TRANSPORT", "bogus")
    monkeypatch.setattr(server.mcp, "run", lambda: pytest.fail("stdio was selected"))
    with pytest.raises(SystemExit, match="FILEVINE_MCP_TRANSPORT") as exc:
        server.main()
    assert "bogus" in str(exc.value)
    assert "stdio" in str(exc.value)
    assert "streamable-http" in str(exc.value)


def test_host_and_port_defaults_and_overrides(monkeypatch):
    assert server._host() == "127.0.0.1"
    assert server._port() == 8080
    monkeypatch.setenv("FILEVINE_MCP_HOST", " 0.0.0.0 ")
    monkeypatch.setenv("PORT", " 9000 ")
    assert server._host() == "0.0.0.0"
    assert server._port() == 9000
    monkeypatch.setenv("PORT", "invalid")
    with pytest.raises(SystemExit, match="PORT must be an integer"):
        server._port()


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_uses_sdk_transport_security(monkeypatch, host):
    monkeypatch.setenv("FILEVINE_MCP_HOST", host)
    assert server._transport_security() is None


@pytest.mark.parametrize("allowed_hosts", [None, "", " , "])
def test_non_loopback_requires_allowed_hosts(monkeypatch, allowed_hosts):
    monkeypatch.setenv("FILEVINE_MCP_HOST", "0.0.0.0")
    if allowed_hosts is not None:
        monkeypatch.setenv("FILEVINE_MCP_ALLOWED_HOSTS", allowed_hosts)
    with pytest.raises(SystemExit, match="FILEVINE_MCP_ALLOWED_HOSTS"):
        server.create_serve_app()


def test_configured_host_and_origin_are_enforced(monkeypatch):
    monkeypatch.setenv("FILEVINE_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv(
        "FILEVINE_MCP_ALLOWED_HOSTS", " 127.0.0.1:8080, mcp.example.test , "
    )
    monkeypatch.setenv("FILEVINE_MCP_ALLOWED_ORIGINS", " https://client.example.test, ")

    async def check():
        async with http_client() as client:
            accepted = await post(
                client, "tools/list", headers={"origin": "https://client.example.test"}
            )
            assert accepted.status_code == 200
            bad_host = await post(
                client, "tools/list", headers={"host": "other.example.test"}
            )
            assert bad_host.status_code == 421
            bad_origin = await post(
                client, "tools/list", headers={"origin": "https://other.example.test"}
            )
            assert bad_origin.status_code == 403

    asyncio.run(check())


def test_missing_origin_allowlist_refuses_supplied_origin(monkeypatch):
    monkeypatch.setenv("FILEVINE_MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("FILEVINE_MCP_ALLOWED_HOSTS", "127.0.0.1:8080")

    async def check():
        async with http_client() as client:
            assert (await post(client, "tools/list")).status_code == 200
            response = await post(
                client, "tools/list", headers={"origin": "https://other.example.test"}
            )
            assert response.status_code == 403

    asyncio.run(check())


def test_loopback_also_rejects_bad_host_and_origin():
    async def check():
        async with http_client() as client:
            bad_host = await post(
                client, "tools/list", headers={"host": "other.example.test"}
            )
            assert bad_host.status_code == 421
            bad_origin = await post(
                client, "tools/list", headers={"origin": "https://other.example.test"}
            )
            assert bad_origin.status_code == 403

    asyncio.run(check())


def test_modern_methods_and_discovery():
    async def check():
        async with http_client() as client:
            for method in ("GET", "DELETE"):
                response = await client.request(
                    method, "/mcp", headers={"mcp-protocol-version": "2026-07-28"}
                )
                assert response.status_code == 405
                assert response.headers["allow"] == "POST"
            response = await post(client, "server/discover")
        result = payload(response)["result"]
        assert "2026-07-28" in result["supportedVersions"]
        info = result["_meta"][SERVER_INFO_META_KEY]
        assert info["name"] == "filevine"
        assert info["title"]
        assert info["version"] == version("filevine-mcp")
        assert "mcp-session-id" not in response.headers

    asyncio.run(check())


def test_unknown_tool_still_returns_is_error():
    async def check():
        async with http_client() as client:
            response = await post(
                client, "tools/call", {"name": "does_not_exist", "arguments": {}}
            )
        assert payload(response)["result"]["isError"] is True

    asyncio.run(check())


def test_tool_cancellation_is_not_swallowed(monkeypatch):
    def cancelled():
        raise asyncio.CancelledError

    monkeypatch.setattr(server, "_c", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(server.mcp.call_tool("get_current_user", {}))


def test_client_disconnect_cancels_http_request(monkeypatch):
    async def check():
        lowlevel = server.mcp._lowlevel_server
        entry = lowlevel.get_request_handler("tools/list")
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocked_list(ctx, params):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        monkeypatch.setitem(
            lowlevel._request_handlers,
            "tools/list",
            type(entry)(entry.params_type, blocked_list),
        )
        headers, body = _modern_request("tools/list")
        headers.update(
            {"host": "127.0.0.1:8080", "accept": "application/json, text/event-stream"}
        )
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/mcp",
            "raw_path": b"/mcp",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (key.encode(), value.encode()) for key, value in headers.items()
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8080),
        }
        body_sent = False

        async def receive():
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return {
                    "type": "http.request",
                    "body": json.dumps(body).encode(),
                    "more_body": False,
                }
            await started.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            pass

        app = server.create_serve_app()
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(app(scope, receive, send), timeout=2)
            assert cancelled.is_set()

    asyncio.run(check())


def test_http_serves_with_uvicorn_and_no_access_log(monkeypatch):
    import uvicorn

    monkeypatch.setenv("FILEVINE_MCP_HOST", "localhost")
    monkeypatch.setenv("PORT", "9001")
    configs = []

    class FakeServer:
        def __init__(self, config):
            configs.append(config)

        async def serve(self):
            pass

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    asyncio.run(server._serve_streamable_http())
    config = configs[0]
    assert config.host == "localhost"
    assert config.port == 9001
    assert config.access_log is False
    assert server.mcp.session_manager.stateless is True
    assert server.mcp.session_manager.json_response is False
