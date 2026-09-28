# MCP 2026-07-28 migration report

## Result

`filevine-mcp` required and received a real migration from MCP `2025-11-25`
to `2026-07-28`. The direct Python SDK dependency changed from
`mcp>=1.28.1,<2` (locked to `1.28.1`) to the exact migration release
`mcp==2.0.0`. The refreshed lock includes the SDK v2 dependency split,
including `mcp-types==2.0.0`.

The authoritative repository-specific change analysis and official citations
are in [`SPEC-DELTA-2026-07-28.md`](SPEC-DELTA-2026-07-28.md). No deployment,
push, browser application, live Filevine account, or live Filevine method was
touched.

## Baseline verdict

The default branch was `main` at `6e8af4d`, matching `origin/main`. Before the
migration:

- `pyproject.toml` constrained SDK v1 and `uv.lock` resolved `mcp==1.28.1`.
- The installed SDK reported `LATEST_PROTOCOL_VERSION == "2025-11-25"`.
- `filevine_mcp/server.py` constructed `FastMCP` and called bare `mcp.run()`,
  exposing the default stdio transport.
- The server registered 147 tools, three static resources, and three prompts.
- There were no tracked test sources and no MCP spec guard. Baseline pytest was
  therefore **0/0 tests** (`no tests ran`, pytest exit 5), while direct Python
  compilation passed.
- Baseline unrestricted Ruff reported 13 pre-existing findings. The migrated
  repository now declares the same focused core policy used by the fleet pilot
  (`E4`, `E7`, `E9`, `F`) against Python 3.10.

This was not a NO-OP candidate.

## Implementation

- Replaced the v1 `FastMCP` import/construction with SDK v2 `MCPServer`.
- Preserved the server name, 147-tool/three-resource/three-prompt primitive set,
  decorator behavior, downstream Filevine credential/token model, and stdio
  `mcp.run()` entry point. No HTTP production mode or MCP session state was
  introduced.
- Retained dual-era support supplied by SDK v2: modern clients negotiate
  `2026-07-28`, while a legacy client still negotiates `2025-11-25`.
- Kept conservative SDK cache defaults (`ttlMs: 0`, `cacheScope: private`) and
  stable decorator registration order.
- Added a lightweight spec guard that pins both the SDK latest revision and the
  `mcp-types` modern revision tuple.
- Refreshed and installed the exact lock. SDK v2 resolves to `mcp==2.0.0` and
  `mcp-types==2.0.0`.

## Spec conformance

The raw-wire suite proves:

- sessionless `server/discover`, supported version, server identity, actual
  primitive capabilities, and no unused extension;
- per-request modern protocol/capability metadata and ordinary
  `resultType: "complete"` results;
- `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name` on modern requests,
  including missing/mismatched method/name rejection;
- `ttlMs: 0` and `cacheScope: private` on tool, prompt, resource,
  resource-template list results and resource reads;
- deterministic listing of all 147 tool names and JSON object input schemas;
- resource-not-found `-32602`, header mismatch `-32020`, unsupported protocol
  `-32022`, and unknown method `-32601`;
- SDK v2 tool-validation result models; and
- modern-default plus explicit legacy negotiation.

The production entry point is stdio-only, so the HTTP assertions use the
SDK-provided in-process Streamable HTTP application as a method-level transport
verification. This does not expose or deploy an HTTP service.

## Canary sibling checks

### A. List-tool limit/order — fixed

The audit classified all 25 `list_*` tools:

- **20 affected and fixed:** seven previously sent unsupported
  `requestedPage`/`pageSize` query names and 13 exposed no pagination control.
  They now expose a schema-bounded `limit` (`1..200`) and appropriate offset or
  cursor, send Filevine's exact vendor parameter names, and defensively trim
  returned `Items`/`ShareLinks` envelopes to the requested total cap.
- **5 clean/N-A:** webhook events, webhook subscriptions, teams, project teams,
  and classifications use finite unpaginated endpoints.
- Ordering controls were added for projects, note comments, and folders;
  comments and folders no longer default toward oldest-first traversal.
- The seven tools that previously exposed `page`/`page_size` retain those
  inputs for caller compatibility and translate them to correct
  `limit`/`offset` values.
- `search_documents` now sends required `searchTerm` and `projectId` plus valid
  limit/offset parameters.

The broader collection audit found 12 affected plural `get_*` tools out of 17;
all 12 now have the same bounded-cap treatment, while the other five are
finite/unpaginated. The locally vendored US, CA, and CJIS specifications have
identical query signatures for the audited endpoints.

### B. Silent rejections — fixed

- All 21 `confirm=False` destructive/financial gates emit one structured,
  PII-free warning with only static tool and reason fields.
- Generic tool argument validation emits a PII-free `invalid_arguments` event
  without raw JSON, IDs, names, amounts, or exception text.
- Missing downstream client credentials, PAT, or organisation ID emit only a
  stable reason code.

### C. Origin/CSP ceremony — N/A

This repository serves no browser page, HTML, static asset, setup web flow,
origin ceremony, or CSP. Its production MCP entry point remains stdio, so the
Sec-Fetch-Site fallback and CSP handoff patterns do not apply.

### D. PII in logs — fixed/clean

- Verification no longer prints a Filevine user's full name, email, or entire
  `/Users/Me` payload.
- Token/API/setup failures no longer include upstream response bodies.
- Invalid arbitrary region input is no longer echoed.
- A source sweep finds no name, email, `sub`, credential, token, or upstream
  response body flowing into a logger. Regression tests use sentinel PII and
  secret markers to prove they stay out of captured logs and CLI output.

## Verification

Verification used the exact lock and required no credentials:

- `uv sync --locked`: passed.
- `uv run pytest -q tests/test_spec_2026_07_28.py`: **7/7 passed**.
- `uv run pytest -q`: **63/63 passed** (all tracked tests; there were no
  pre-existing tracked tests).
- `uv run python tests/spec_check.py`: passed for `2026-07-28`.
- `uv run --with ruff ruff check .`: all checks passed.
- Python compilation and SDK/server import inspection passed; the installed
  versions report `mcp==2.0.0`, `mcp-types==2.0.0`, and 147 registered tools.

Live Filevine behavior remains **method-verified only** against the locally
vendored Filevine API descriptions and mocked request/response regressions. A
credentialed live-account smoke test was intentionally not run.

## Git and handoff

The runtime permits worktree edits but denies writes to this repository's
`.git` directory. The initial real-branch creation failed on `.git/index.lock`
with `Operation not permitted`. Per the task's sandbox-wall procedure, commits
were built in an alternate Git database on branch `spec-2026-07-28` and a
verified portable bundle is exported to the requested scratchpad path.

Commits, in order:

1. `3083883 docs: document MCP 2026-07-28 delta`
2. `8f31ecf feat: migrate server to MCP 2026-07-28`
3. `7da2308 test: prove MCP 2026-07-28 conformance`
4. `docs: report MCP 2026-07-28 migration` (this report commit)

Every commit is a Conventional Commit and includes
`Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. Nothing was pushed.
The bundle must be imported into the repository's real Git database before the
branch is available there.
