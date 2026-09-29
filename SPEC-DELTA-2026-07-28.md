# MCP 2026-07-28 protocol notes

The project requires `mcp>=2.2,<3`; `uv.lock` resolves `mcp` and `mcp-types`
to `2.2.0`. `filevine_mcp/server.py` constructs `MCPServer` and runs it over
stdio. The [official changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
and [Python SDK migration guide](https://py.sdk.modelcontextprotocol.io/migration/)
describe the protocol and SDK changes. The [migration report](SPEC-MIGRATION-REPORT.md)
contains reproducible local checks and their scope.

## Protocol surfaces used here

| Change                                                                                                                                   | Repository mapping                                                                                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Modern requests are sessionless and carry protocol/capability metadata. Servers implement `server/discover`; results carry `resultType`. | The SDK handles modern dispatch and discovery. Tests check server identity, negotiated versions, capabilities, ordinary `complete` results, and legacy negotiation. Downstream Filevine credential and token state is separate from MCP sessions. |
| Streamable HTTP requests use `MCP-Protocol-Version`, `Mcp-Method`, and, for named operations, `Mcp-Name`.                                | The production entry point remains stdio. In-process HTTP tests check required headers and mismatches; no tool parameter opts into `x-mcp-header`.                                                                                                |
| Tool, prompt, resource, and resource-template listings and resource reads include cache metadata.                                        | Tests check the SDK's conservative `ttlMs: 0` and `cacheScope: private` values.                                                                                                                                                                   |
| `tools/list` should be deterministic; tool input schemas accept JSON Schema 2020-12 keywords.                                            | Registration order is stable. Tests check repeated names and generated object schemas; tool success payloads remain JSON strings and validation failures return safe MCP tool errors.                                                             |
| Errors use revised codes.                                                                                                                | Tests cover unknown resource `-32602`, header mismatch `-32020`, unsupported version `-32022`, and unknown method `-32601`.                                                                                                                       |
| Capabilities can declare extensions.                                                                                                     | Discovery advertises the registered tool, resource, and prompt capabilities without an unused extension.                                                                                                                                          |

The server does not implement MCP tasks, MRTR, roots, sampling, elicitation,
MCP authorization, dynamic client registration, protocol logging,
subscriptions, or an HTTP event store. No browser origin or CSP flow is
served. Filevine OAuth is downstream vendor authentication rather than MCP
transport authorization.

## Application behavior covered by tests

Collection tools expose bounded limits and appropriate offset or cursor
controls. The seven tools that already accepted `page` and `page_size` still
accept them and translate them to Filevine request parameters. Where ordering
is supported, projects, note comments, and folders accept explicit ordering;
comments and folders no longer default to oldest-first traversal.
`search_documents` sends `searchTerm`, `projectId`, limit, and offset.
Responses are trimmed to the requested cap when returned in `Items` or
`ShareLinks` envelopes. Some endpoints are finite and unpaginated.

Destructive and financial tools with `confirm=False` return a safe MCP tool
error and log a structured warning without user data. Argument-validation and missing-credential logs use
stable reason codes. Setup verification omits user profile fields; token and
API failures omit upstream response bodies. The tests use sentinel values to
check these local diagnostic paths.
