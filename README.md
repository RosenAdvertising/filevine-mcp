# filevine-mcp

[![PyPI version](https://img.shields.io/pypi/v/filevine-mcp.svg)](https://pypi.org/project/filevine-mcp/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

MCP server for [Filevine](https://filevine.com) — full API coverage for legal case management. Use Filevine from Claude Desktop with natural language.

## What you can do

- **Projects (Matters)** — create, update, archive, manage vitals, custom forms, collections
- **Contacts** — full CRUD, addresses, emails, phones, project associations
- **Tasks** — create, assign, complete, pin, snooze, manage by project or user
- **Notes** — create, pin, comment, tag management
- **Documents** — CRUD, revisions, lock/unlock, batch upload/download, search, share links
- **Folders** — organise documents in folder hierarchies
- **Billing** — billing items, invoices, payments, trust funds, rate schedules
- **Project Teams** — assign and manage team members per project
- **Appointments & Deadlines** — schedule and track on matters
- **Emails** — log email communications to projects
- **Webhooks** — subscribe to Filevine events for real-time notifications
- **Teams** — manage organisation teams
- **Reference data** — project types, document series, classifications, reports

## Requirements

- Python 3.10+
- Python MCP SDK >=2.3,<3 (supports the MCP 2026-07-28 protocol)
- Claude Desktop (or any MCP-compatible client)
- Filevine API credentials (Client ID, Client Secret)
- Filevine region: `us`, `ca`, or `cjis`

> **Filevine API access:** Obtain credentials from your Filevine organisation administrator or developer portal.

## Installation

```bash
pip install filevine-mcp
```

## Setup

```bash
filevine-mcp-setup
```

This prompts for your Client ID, Client Secret, Org ID, and region, then
tests the credentials and saves them through the configured credential store.

Verify:

```bash
filevine-mcp-verify
```

## Claude Desktop Configuration

```json
{
  "mcpServers": {
    "filevine": {
      "command": "filevine-mcp"
    }
  }
}
```

## HTTP mode

The default transport is stdio. To serve stateless Streamable HTTP, set
`FILEVINE_MCP_TRANSPORT=streamable-http`. The MCP endpoint is `/mcp`; the SDK
supports both modern and legacy clients on this endpoint and keeps its default
SSE responses so disconnecting clients cancel their requests.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FILEVINE_MCP_TRANSPORT` | `stdio` | Select `stdio` or `streamable-http`. |
| `FILEVINE_MCP_HOST` | `127.0.0.1` | HTTP bind address. |
| `PORT` | `8080` | HTTP port (integer). |
| `FILEVINE_MCP_ALLOWED_HOSTS` | Unset | Comma-separated Host header values; required for non-loopback binds. Include the port when clients send it, or use `mcp.example.com:*`. |
| `FILEVINE_MCP_ALLOWED_ORIGINS` | Unset | Comma-separated allowed origins, such as `https://client.example.com`; on non-loopback binds, supplied origins are refused unless allowed. |
| `FILEVINE_CLIENT_ID` | Stored credential | Filevine client ID. |
| `FILEVINE_CLIENT_SECRET` | Stored credential | Filevine client secret. |
| `FILEVINE_PAT` | Stored credential | Filevine personal access token. |
| `FILEVINE_ORG_ID` | Stored credential | Filevine organization ID. |
| `FILEVINE_REGION` | `us` | Filevine region: `us`, `ca`, or `cjis` (also resolved from stored configuration). |
| `FILEVINE_MCP_USE_KEYRING` | `1` | Set to `0` to use the existing environment/file credential fallback. |
| `FILEVINE_ALLOWED_DESTINATION_HOSTS` | Unset | Existing allowlist for vendor destination URLs, described below. |

HTTP mode uses the same server-side vendor credentials and credential store as
stdio. Request headers and bodies do not supply Filevine credentials. On
`127.0.0.1`, `localhost`, or `::1`, the SDK validates loopback Host and Origin
headers automatically. Other bind addresses require the explicit allowlists
above; requests without an Origin header remain accepted for allowed hosts.

After configuring credentials with the existing setup command:

```bash
FILEVINE_MCP_TRANSPORT=streamable-http FILEVINE_MCP_HOST=127.0.0.1 PORT=8080 filevine-mcp
```

Connect the MCP client to `http://127.0.0.1:8080/mcp`.

## Credential storage

By default credentials are stored in your operating system's native secret store
via the cross-platform [`keyring`](https://github.com/jaraco/keyring) library:

| OS      | Backend                                  |
| ------- | ---------------------------------------- |
| macOS   | Keychain                                 |
| Windows | Credential Manager                       |
| Linux   | Secret Service (GNOME Keyring / KWallet) |

Secrets saved to the keyring use the service name `filevine-mcp`.

**File fallback.** On a host with no keyring backend (e.g. a headless Linux box
without Secret Service), or if you set `FILEVINE_MCP_USE_KEYRING=0`, credentials
fall back to a `~/.filevine-mcp/.env` file with `0600` permissions.

On Windows, the file is stored in the user's profile and protected by Windows'
default per-user access rules. On POSIX, files are created with `0600` permissions
and writes fail closed if private permissions cannot be established.

**Read order.** Credentials resolve in the order OS keyring → process environment
→ `.env` file. So a rotated secret in the keyring always wins, and a
`FILEVINE_CLIENT_ID` / `FILEVINE_CLIENT_SECRET` exported in your shell overrides
the file fallback without touching the keyring.

## Authentication Notes

Filevine uses OAuth 2.0 **client credentials** flow — no browser authorization required. Tokens are fetched automatically and refreshed when they expire. Three regions are supported with separate API and identity hosts:

| Region | API Host            | Identity Host            |
| ------ | ------------------- | ------------------------ |
| us     | api.filevineapp.com | identity.filevine.com    |
| ca     | api.filevineapp.ca  | identity.filevine.ca     |
| cjis   | api.filevinegov.com | identity.filevinegov.com |

## Example usage in Claude

> "List my open projects"
>
> "Create a task on project 456 — send retainer agreement to client"
>
> "Get the billing vitals for project 789"
>
> "Add a note to project 123 — client called re: mediation date"
>
> "Search documents for 'deposition transcript'"
>
> "List all webhook event types available"

## License

MIT

### Approved destination URLs

Set `FILEVINE_ALLOWED_DESTINATION_HOSTS` in the server environment, for example
`FILEVINE_ALLOWED_DESTINATION_HOSTS=hooks.firm.example,.integrations.firm.example`.
Comma-separated exact hosts allow only that host; a leading dot allows the domain
and its subdomains. Matching ignores case and trailing dots and normalizes IDNA.
An empty or unset list refuses destination URLs before any request. HTTPS, no
userinfo, and public literal addresses remain required. This administrator-owned
list prevents model-supplied destinations from sending data to arbitrary hosts,
including private-address DNS aliases and unapproved redirectors. Approve only
hosts whose DNS and redirects the firm trusts; the vendor executes requests later.
Tools cannot change this setting.

`FILEVINE_REGION` and setup accept only `us`, `ca`, or `cjis`. Values are trimmed and lowercased; unknown values
fail with an error; they never select a different region. Webhook destinations
in `fields_json` use an explicit set of destination aliases, validated by the
same allowlist even inside nested objects and arrays. Unrelated fields such as
`securityLevel` and `jurisdiction` pass unchanged.
