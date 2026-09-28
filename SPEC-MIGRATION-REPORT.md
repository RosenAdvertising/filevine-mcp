# MCP 2026-07-28 migration

## Current implementation

The project requires the Python MCP SDK `mcp>=2.2,<3`. The committed `uv.lock`
resolves both `mcp` and its companion `mcp-types` to `2.2.0`. The server uses
`MCPServer`, retains its stdio entry point, and registers tools, resources, and
prompts through SDK decorators. Modern clients use protocol `2026-07-28`; the
SDK also supports legacy negotiation. See the [protocol delta](SPEC-DELTA-2026-07-28.md)
for the repository-specific mapping of protocol changes.

The migration also bounds Filevine collection requests and returned items,
corrects pagination and ordering parameters, and keeps sensitive values out of
application diagnostics. Seven existing list tools retain their `page` and
`page_size` inputs for caller compatibility. Tests cover these mappings with
recorded requests and fake responses; they do not establish live Filevine API
behavior.

The production command uses stdio. Protocol tests exercise the SDK's
in-process Streamable HTTP application to check wire behavior; they do not
configure an HTTP production endpoint. The server has no MCP session state.

## Reproduce local checks

With the committed lock installed into `.venv`, run these commands from the
repository root. The dummy values keep credential lookup on process
environment variables; tests replace outbound Filevine requests with fakes.

```sh
FILEVINE_CLIENT_ID=offline-test-client FILEVINE_CLIENT_SECRET=offline-test-secret \
FILEVINE_ORG_ID=offline-test-org FILEVINE_REGION=us \
FILEVINE_PAT=offline-test-pat PYTHONDONTWRITEBYTECODE=1 \
.venv/bin/pytest -q -p no:cacheprovider tests
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/spec_check.py
.venv/bin/ruff check filevine_mcp/client.py filevine_mcp/server.py \
  filevine_mcp/setup/oauth_flow.py filevine_mcp/setup/verify.py \
  tests/spec_check.py tests/test_list_tool_controls.py \
  tests/test_logging_privacy.py tests/test_spec_2026_07_28.py
uv lock --check --offline
```

The suite covers local protocol handling, bounded request construction, and
sanitized diagnostics. It does not test a credentialed Filevine account,
deployed transport, or every platform selected by lockfile markers.

## Open product decision

MCP 2.2.0 masks messages from tool exceptions other than `ToolError` or
`ResourceError`. Retaining that masking limits leakage; raising explicitly
safe `ToolError` messages could give clients more actionable feedback. Toby
should choose the desired policy. Existing tool exception handling is
unchanged by this documentation cleanup.
