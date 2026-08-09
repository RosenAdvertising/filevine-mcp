# MCP specification delta: 2025-11-25 to 2026-07-28

Research date: 2026-08-09. Sources are limited to the official MCP
specification and the official MCP Python SDK documentation and repository.

## Current target and migration release

This repository targets MCP `2025-11-25`, not `2026-07-28`:

- `pyproject.toml` declares `mcp>=1.28.1,<2`, and `uv.lock` resolves the MCP
  Python SDK to `1.28.1`.
- The installed SDK reports `LATEST_PROTOCOL_VERSION == "2025-11-25"`.
- `filevine_mcp/server.py` constructs the v1 `FastMCP` class and relies on the
  SDK default protocol negotiation.
- The only configured transport is `mcp.run()`'s default stdio transport. The
  repository has no tracked protocol tests or protocol-version guard.

The official changelog identifies `2026-07-28` as the revision following
`2025-11-25` ([spec changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)).
The implementation release is MCP Python SDK `2.0.0`, whose release notes say
it supports `2026-07-28` and all earlier revisions from one server
([SDK v2.0.0 release notes](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.0.0)).
Required source changes follow the official
[v1-to-v2 migration guide](https://py.sdk.modelcontextprotocol.io/migration/).

Verdicts below mean:

- **AFFECTS-US**: this server exposes or relies on the changed surface. The SDK
  may implement the wire behavior, but the migration must pin, configure, or
  test it.
- **NOT-APPLICABLE**: the feature or direction is not implemented here and
  will not be added merely because the revision permits it.

## Protocol negotiation and lifecycle

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Modern MCP removes protocol-level sessions and `Mcp-Session-Id`; application state must use explicit handles. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | The server must handle independent modern stdio requests. Its only state is downstream Filevine credential/token state; it has no MCP session state, so the migration preserves that posture. |
| Modern requests remove `initialize` / `notifications/initialized` and carry protocol version, client capabilities, and recommended identity metadata on every request/result. Version mismatch uses `UnsupportedProtocolVersionError`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | SDK v2 must provide dual-era dispatch: self-describing modern requests and a legacy negotiation path. Raw-wire tests must exercise both. |
| Servers MUST implement `server/discover` with supported versions, capabilities, and identity. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | This is required for every modern server. Discovery must identify `filevine`, advertise `2026-07-28`, and match the primitives actually registered. |
| Every result requires `resultType`: `"complete"` or MRTR's `"input_required"`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **AFFECTS-US** | Tools, resources, prompts, discovery, and list methods return results. Ordinary responses must serialize `resultType: "complete"`. |
| Server-initiated requests are replaced by Multi Round-Trip Requests (MRTR). [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | No tool, resource, or prompt uses roots, sampling, elicitation, or another server-to-client request. MRTR will not be added as a feature. |
| `ping`, `logging/setLevel`, and `notifications/roots/list_changed` are removed; protocol logging becomes request-opt-in. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | The application implements none of these methods and does not emit MCP logging notifications. PII-free application logs remain on stderr. |

## Transports and notifications

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Streamable HTTP POST requests require `Mcp-Method` and, for named operations, `Mcp-Name`; `x-mcp-header` permits selected tool parameters to populate custom HTTP headers. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | Although the shipped entry point remains stdio, the SDK server surface can be embedded in Streamable HTTP. Raw-wire HTTP tests must prove required/mismatched header handling. No Filevine tool parameter opts into `x-mcp-header`. |
| Standalone HTTP GET and resource subscribe/unsubscribe are replaced by `subscriptions/listen`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | The v1 server advertises all list-change and resource-subscription capability flags as false and has no publisher, event store, or custom bus. The migration will preserve that posture rather than add a subscription feature. |
| SSE resumption/redelivery is removed. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | The server configures no event store and depends on no resumed HTTP stream. |
| Legacy HTTP+SSE is deprecated. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | The repository exposes stdio only and contains no HTTP+SSE transport. |

## Capabilities and extensions

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Client and server capabilities gain an `extensions` field. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | `server/discover` exposes the shape. This migration adds no extension, so discovery must not advertise one. |
| Experimental core tasks move to `io.modelcontextprotocol/tasks` and change method shape. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#major-changes) | **NOT-APPLICABLE** | Filevine task tools are ordinary downstream API tools, not MCP task handlers or task-augmented tools. |
| Roots, Sampling, and Logging are deprecated. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | None is declared or used. |
| Sampling `includeContext` values `thisServer` and `allServers` are deprecated. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | Sampling is not used. |

## Tools, resources, prompts, and cache semantics

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Tool, prompt, resource, resource-template list results and resource reads require `ttlMs` and `cacheScope`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The server registers 147 tools, three resources, and three prompts. SDK v2's conservative private, zero-TTL defaults must appear on each applicable result. |
| `tools/list` SHOULD be deterministic. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | Registration order is stable. Repeated raw listings must preserve all 147 names in the same order. |
| Tool schemas accept JSON Schema 2020-12 keywords; structured content may be any JSON value. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | Decorators generate schemas for every tool. Existing success and validation-error payloads are JSON strings, not structured content; SDK v2 owns the revised schema validation and tests must prove generated object schemas and string results remain valid. |
| Resource-not-found changes from `-32002` to JSON-RPC Invalid Params `-32602`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The server publishes static resources. Unknown URIs must now return `-32602`. |
| URL-mode elicitation removes its completion notification and ID. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The server performs no elicitation. |
| Generated meta-schema numeric bounds/defaults now use numbers rather than integers. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#other-schema-changes) | **NOT-APPLICABLE** | This repository neither vendors nor directly validates against the generated MCP meta-schema. SDK v2 absorbs the correction. |

## Authorization and security

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| Authorization servers should return RFC 9207 `iss`, and MCP clients must validate a present issuer before redemption. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | This MCP server exposes no MCP authorization server/client. Its Filevine OAuth client-credentials/PAT exchange is downstream vendor authentication, outside MCP transport authorization. |
| MCP clients using Dynamic Client Registration must send `application_type`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The code does not dynamically register an MCP client. |
| Persisted MCP client credentials must be keyed to their authorization-server issuer. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | The repository stores downstream Filevine credentials only; it persists no MCP client registrations. |
| Dynamic Client Registration is deprecated in favor of Client ID Metadata Documents. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#deprecated) | **NOT-APPLICABLE** | The server neither hosts DCR nor acts as a dynamically registered MCP client. |

## Errors, metadata, and observability

| Normative change | Verdict | Repository-specific reason |
| --- | --- | --- |
| MCP reserves `-32020..-32099`; header mismatch, missing capability, and unsupported version become `-32020`, `-32021`, and `-32022`; unknown methods use `-32601`. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **AFFECTS-US** | The SDK dispatch surface can receive bad routing headers, unsupported versions, and unknown methods. Tests will cover reachable cases without inventing an optional capability. |
| `_meta` formally carries W3C trace context. [Source](https://modelcontextprotocol.io/specification/2026-07-28/changelog#minor-changes) | **NOT-APPLICABLE** | There is no MCP tracing integration. This migration will not add one. |

Governance and SEP-process changes impose no runtime requirement and are
therefore omitted from the verdict tables. The feature lifecycle is respected
by not adding deprecated roots, sampling, logging, HTTP+SSE, or DCR features.

## SDK v2 port surface

The official migration guide identifies the repository's required source
adaptations:

- `FastMCP` is renamed to `MCPServer`; tool/resource/prompt decorators remain.
- `MCPServer.call_tool()` returns a `CallToolResult`, accepts an optional
  `context`, and sync handlers run in a worker thread.
- Transport-specific settings move from the constructor to `run()` or the
  application factory. This server has no constructor transport options, so
  its `run()` remains the stdio default.
- SDK types use snake-case Python fields while the wire format remains
  camel-case.
- SDK v2 validates result models and exposes dual-era protocol handling. Tests
  must target raw modern requests plus a legacy negotiation regression.
