# Filevine MCP server

[![CI](https://github.com/RosenAdvertising/filevine-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/RosenAdvertising/filevine-mcp/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP 2026-07-28](https://img.shields.io/badge/MCP-2026--07--28-7C3AED.svg)](https://modelcontextprotocol.io)
[![PyPI version](https://img.shields.io/pypi/v/filevine-mcp.svg)](https://pypi.org/project/filevine-mcp/)

Connect Claude and other MCP clients to Filevine to manage projects, contacts, documents, tasks and billing.

Filevine MCP server is a [Model Context Protocol](https://modelcontextprotocol.io) server for [Filevine](https://filevine.com), the legal case management platform. It registers 147 tools that read and write Filevine data. It runs over stdio by default, for desktop clients such as Claude Desktop, and offers an opt-in stateless Streamable HTTP mode that implements MCP specification 2026-07-28. Filevine credentials stay on the machine that runs the server: they come from the setup command and your operating system's keyring, never from the client.

## Features

- **Projects (matters)**: create, update, archive and look up projects, with vitals, custom forms, collections, deadlines and appointments.
- **Contacts**: create, update and look up contacts with addresses, emails, phones and project associations.
- **Tasks**: create, assign, complete, pin and snooze tasks, by project or user.
- **Notes**: create, update and pin notes, add comments, and create or remove tags.
- **Documents and folders**: create, update, lock, unlock, move, copy and search documents, add revisions, batch upload and download, create share links, and organize documents in folders.
- **Billing**: billing items, invoices, payments, project funds and transactions, and rate schedules.
- **Teams**: manage project teams and organization teams.
- **Email**: log email to projects, list project emails, and work with mailroom items.
- **Webhooks**: subscribe to Filevine events for real-time notifications.
- **Reference data and reports**: project types, document series, classifications and reports.

## Tools

The server registers 147 tools.

21 of them delete, archive or remove records, change billing items, or finalize, approve or pay invoices. They take a `confirm` argument; without `confirm=true` they return an error and change nothing, for example "archive_project requires confirm=True. Confirm this action with the user before proceeding."

<details>
<summary>All 147 tools</summary>

- `add_contact_to_project`
- `add_document_revision`
- `add_document_to_project`
- `add_email_to_project`
- `add_team_member_to_project`
- `approve_invoice`
- `archive_project`
- `assign_task`
- `batch_download_documents`
- `batch_upload_documents`
- `complete_task`
- `confirm_batch_upload`
- `copy_documents`
- `create_billing_item`
- `create_collection_item`
- `create_contact`
- `create_document`
- `create_folder`
- `create_hashtag`
- `create_invoice`
- `create_mailroom_item`
- `create_note`
- `create_note_comment`
- `create_payment`
- `create_payment_and_apply`
- `create_project`
- `create_project_appointment`
- `create_project_deadline`
- `create_share_link`
- `create_task`
- `create_team`
- `create_webhook_subscription`
- `delete_billing_item`
- `delete_collection_item`
- `delete_document`
- `delete_folder`
- `delete_invoice`
- `delete_project_deadline`
- `delete_share_link`
- `delete_task`
- `delete_team`
- `delete_webhook_subscription`
- `finalize_invoice`
- `get_billing_item`
- `get_collection_item`
- `get_contact`
- `get_contact_addresses`
- `get_contact_emails`
- `get_contact_phones`
- `get_contact_projects`
- `get_countries`
- `get_current_user`
- `get_document`
- `get_document_download_locator`
- `get_document_series`
- `get_folder`
- `get_invoice_pdf`
- `get_note`
- `get_note_comment`
- `get_org_billing_codes`
- `get_org_billing_settings`
- `get_org_rate_schedules`
- `get_payment_link`
- `get_project`
- `get_project_billing_codes`
- `get_project_billing_settings`
- `get_project_billing_vitals`
- `get_project_contacts`
- `get_project_deadline`
- `get_project_form`
- `get_project_fund_transactions`
- `get_project_funds`
- `get_project_invoices`
- `get_project_team`
- `get_project_team_member`
- `get_project_transactions`
- `get_project_type`
- `get_project_vitals`
- `get_report`
- `get_share_link`
- `get_task`
- `get_team`
- `get_user`
- `get_user_appointments`
- `get_user_project_access`
- `get_user_recent_projects`
- `get_user_tasks`
- `get_webhook_subscription`
- `incomplete_task`
- `list_classifications`
- `list_collection_items`
- `list_contacts`
- `list_document_series`
- `list_documents`
- `list_folders`
- `list_mailroom`
- `list_note_comments`
- `list_notes`
- `list_project_appointments`
- `list_project_deadlines`
- `list_project_emails`
- `list_project_notes`
- `list_project_tasks`
- `list_project_teams`
- `list_project_types`
- `list_projects`
- `list_recently_opened_documents`
- `list_reports`
- `list_share_links`
- `list_tasks`
- `list_teams`
- `list_users`
- `list_webhook_events`
- `list_webhook_subscriptions`
- `lock_document`
- `mark_invoice_sent`
- `move_documents`
- `pin_note`
- `pin_note_to_project`
- `pin_task`
- `remove_contact_from_project`
- `remove_project_team_member`
- `remove_tag_from_contacts`
- `remove_tag_from_documents`
- `remove_tag_from_notes`
- `search_documents`
- `set_project_rate_schedule`
- `snooze_task`
- `unlock_document`
- `unpin_note`
- `unpin_note_from_project`
- `unpin_task`
- `update_billing_item`
- `update_collection_item`
- `update_contact`
- `update_document`
- `update_folder`
- `update_invoice`
- `update_note`
- `update_note_comment`
- `update_project`
- `update_project_contact`
- `update_project_deadline`
- `update_project_form`
- `update_project_team_member`
- `update_task`
- `update_webhook_subscription`

</details>

### Prompts and resources

The server also registers three prompts and three resources.

| Prompt | What it does |
| --- | --- |
| `billing_workflow` | Guides a billing workflow for one project: review items, finalize the invoice, record the payment. Takes `project_id`. |
| `daily_briefing` | Morning briefing: open projects needing attention, overdue tasks and pending billing. |
| `intake_triage` | Reviews a new project's contacts, tasks, documents and billing setup. Takes `project_id`. |

| Resource | What it provides |
| --- | --- |
| `filevine://classifications` | All document classification categories configured in your Filevine organisation. |
| `filevine://project_types` | All project (matter) types configured in your Filevine organisation. |
| `filevine://security-notes` | Security notes for the server. |

## Requirements

- Python 3.10+.
- Filevine API credentials from your Filevine organisation administrator or developer portal: a client ID, a client secret and a personal access token (PAT), plus your organization ID.
- Your Filevine region: `us`, `ca` or `cjis`.
- An MCP client such as Claude Desktop.

## Installation

Install [uv](https://docs.astral.sh/uv/), then clone the repository and install its locked dependencies:

```bash
git clone https://github.com/RosenAdvertising/filevine-mcp.git
cd filevine-mcp
uv sync --locked
```

Releases are also published to PyPI: `pip install filevine-mcp` installs version 0.3.0, which predates the HTTP mode described below. Install from source to use HTTP mode.

## Configuration

Run the setup command once. It prompts for your region, client ID, client secret, personal access token and organization ID, tests the credentials against Filevine, and saves them through the credential store (see [Credential storage](#credential-storage)):

```bash
uv run filevine-mcp-setup
```

Check the connection:

```bash
uv run filevine-mcp-verify
```

Server messages that say to run `filevine-mcp-setup` mean `uv run filevine-mcp-setup` from your clone.

The server reads these variables, which you can also set in its environment:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `FILEVINE_CLIENT_ID` | Yes (saved by setup) | Credential store | Filevine client ID. |
| `FILEVINE_CLIENT_SECRET` | Yes (saved by setup) | Credential store | Filevine client secret. |
| `FILEVINE_PAT` | Yes (saved by setup) | Credential store | Filevine personal access token. |
| `FILEVINE_ORG_ID` | Yes (saved by setup) | Credential store | Filevine organization ID. |
| `FILEVINE_REGION` | No | `us` | Filevine region: `us`, `ca` or `cjis`. Also resolved from the credential store. |
| `FILEVINE_MCP_USE_KEYRING` | No | `1` | Set to `0` to skip the operating system keyring and use the environment and the `.env` file fallback. |
| `FILEVINE_ALLOWED_DESTINATION_HOSTS` | No | Unset | Administrator allowlist for webhook destination hosts (see [Webhook destination allowlist](#webhook-destination-allowlist)). |

## Usage with Claude Desktop

Add the server to Claude Desktop's configuration file (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "filevine": {
      "command": "uv",
      "args": ["run", "--locked", "--directory", "/absolute/path/to/filevine-mcp", "filevine-mcp"]
    }
  }
}
```

Replace `/absolute/path/to/filevine-mcp` with the path of your clone, then restart Claude Desktop. Any other stdio MCP client uses the same command and arguments.

## HTTP mode

Stdio is the default. Set `FILEVINE_MCP_TRANSPORT=streamable-http` to serve the stateless Streamable HTTP transport from MCP specification 2026-07-28 at `/mcp`. Each request stands alone: no initialization handshake and no `Mcp-Session-Id`. Clients on earlier protocol versions are served on the same endpoint.

> **Security: this endpoint has no authentication and no TLS.** Anyone who can reach the port can run every tool, including write and delete tools, with this server's vendor credentials. Keep the default loopback bind (`127.0.0.1`), or put the server behind an authenticating TLS proxy on a private network. `FILEVINE_MCP_ALLOWED_HOSTS` and `FILEVINE_MCP_ALLOWED_ORIGINS` protect against browser DNS rebinding, not against direct callers. A proxy in front of it needs connection and idle timeouts: a legacy-style `GET /mcp` with `Accept: text/event-stream` holds a stream open until the client disconnects.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FILEVINE_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. |
| `FILEVINE_MCP_HOST` | `127.0.0.1` | Bind address. `127.0.0.1`, `localhost` and `::1` use the SDK's built-in Host and Origin checks; any other value requires `FILEVINE_MCP_ALLOWED_HOSTS`. |
| `PORT` | `8080` | Port; must be an integer. |
| `FILEVINE_MCP_ALLOWED_HOSTS` | unset | Comma-separated `Host` header values accepted on a non-loopback bind, such as `mcp.example.com:8080` or `mcp.example.com:*`. |
| `FILEVINE_MCP_ALLOWED_ORIGINS` | unset | Comma-separated `Origin` values accepted on a non-loopback bind, such as `https://client.example.com`. Requests without an `Origin` header are accepted. |

Filevine credentials come from the same configuration as stdio (see [Configuration](#configuration)), never from the request.

```bash
FILEVINE_MCP_TRANSPORT=streamable-http PORT=8080 uv run --locked filevine-mcp
```

Point the MCP client at `http://127.0.0.1:8080/mcp`. Responses use the SDK's default streaming mode, so a client that disconnects cancels its request.

## Error handling

A failed tool call returns an MCP error result (`isError`) with a fixed message. Errors raised while a tool runs start with `Error executing tool <name>: ` followed by the message in the table below; argument-validation messages are returned without that prefix. The server never passes a Filevine response body, a request URL, a credential or an input value back to the client.

| Situation | What the tool returns |
| --- | --- |
| Setup missing or incomplete | "FILEVINE_CLIENT_ID and FILEVINE_CLIENT_SECRET are required. Run: filevine-mcp-setup", "FILEVINE_PAT is required. Run: filevine-mcp-setup" or "FILEVINE_ORG_ID is required. Run filevine-mcp-setup." |
| Authorization failed (HTTP 401, after one automatic token request and retry) | "Filevine authorization failed (401). Re-run filevine-mcp-setup to reauthorize." |
| Access denied (HTTP 403) | "Filevine access denied: the connected account lacks permission for this action (or the authorization expired; re-run filevine-mcp-setup if so)." |
| Rate limited (HTTP 429) | "Filevine rate limit reached. Retry after N seconds." where N comes from the `Retry-After` header. |
| Any other HTTP error status | "Filevine request failed with HTTP 500. Check account permissions and request details." (the status varies). |
| Timeout or connection failure on a read | "Filevine request timed out or lost its connection. Check connectivity and retry." |
| Timeout or connection failure on a write | "Filevine request timed out or lost its connection; the outcome is unknown. Check whether it completed before retrying." |
| Response that is not valid JSON | "Filevine returned an unreadable response." |
| Missing `confirm=true` on a guarded tool | "archive_project requires confirm=True. Confirm this action with the user before proceeding." (the tool name varies). |
| Webhook destination not approved | "Destination must be a public HTTPS URL approved by FILEVINE_ALLOWED_DESTINATION_HOSTS; configure trusted hostnames." |
| Invalid arguments | A message such as "Invalid argument 'limit'; expected integer greater than or equal to 1 and less than or equal to 200." |
| Anything else | "Filevine request failed unexpectedly. Check configuration and try again." |

Every Filevine request has a 30-second timeout. On HTTP 429 the server waits for the `Retry-After` interval (10 seconds when the header is missing) and retries, up to 3 times per request and 60 seconds of total waiting; if the next wait would exceed what is left, the tool returns the rate-limit message at once. On HTTP 401 it requests a new access token once and repeats the request. It does not retry timeouts, connection failures or 5xx responses. A failed resource read returns "Filevine resource could not be read. Check configuration and try again."

At startup the server exits with a message on stderr and a non-zero status when `FILEVINE_MCP_TRANSPORT` is neither `stdio` nor `streamable-http`, when `PORT` is not an integer, or when a non-loopback `FILEVINE_MCP_HOST` is set without `FILEVINE_MCP_ALLOWED_HOSTS`.

## Credential storage

By default credentials are stored in your operating system's native secret store
via the cross-platform [`keyring`](https://github.com/jaraco/keyring) library:

| OS      | Backend                                  |
| ------- | ---------------------------------------- |
| macOS   | Keychain                                 |
| Windows | Credential Manager                       |
| Linux   | Secret Service (GNOME Keyring / KWallet) |

Secrets saved to the keyring use the service name `filevine-mcp`.

The Filevine access token is cached separately in `~/.filevine-mcp/tokens.json` with `0600` permissions, whichever backend holds the credentials.

**File fallback.** On a host with no keyring backend (e.g. a headless Linux box
without Secret Service), or if you set `FILEVINE_MCP_USE_KEYRING=0`, credentials
fall back to a `~/.filevine-mcp/.env` file with `0600` permissions.

On Windows, the file is stored in the user's profile and protected by Windows'
default per-user access rules. On POSIX, files are created with `0600` permissions
and writes fail closed if private permissions cannot be established.

**Read order.** A credential already set in the process environment wins. Otherwise the server reads the OS keyring, then the `.env` file fallback. To make a secret rotated in the keyring take effect, unset `FILEVINE_CLIENT_ID` and `FILEVINE_CLIENT_SECRET` in the shell that starts the server.

## Authentication notes

Filevine authorizes with a personal access token (PAT) together with your client ID and client secret: the server posts them to your region's identity host (`/connect/token`) and receives an access token. No browser authorization is required. Access tokens are cached and requested again when they expire. Three regions are supported with separate API and identity hosts:

| Region | API Host            | Identity Host            |
| ------ | ------------------- | ------------------------ |
| us     | api.filevineapp.com | identity.filevine.com    |
| ca     | api.filevineapp.ca  | identity.filevine.ca     |
| cjis   | api.filevinegov.com | identity.filevinegov.com |

`FILEVINE_REGION` and setup accept only `us`, `ca`, or `cjis`. Values are trimmed and lowercased; unknown values fail with an error; they never select a different region.

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

## Webhook destination allowlist

Set `FILEVINE_ALLOWED_DESTINATION_HOSTS` in the server environment, for example `FILEVINE_ALLOWED_DESTINATION_HOSTS=hooks.firm.example,.integrations.firm.example`. Comma-separated exact hosts allow only that host; a leading dot allows the domain and its subdomains. Matching ignores case and trailing dots and normalizes IDNA. An empty or unset list refuses destination URLs before any request. HTTPS, no userinfo, and public literal addresses remain required. This administrator-owned list prevents model-supplied destinations from sending data to arbitrary hosts, including private-address DNS aliases and unapproved redirectors. Approve only hosts whose DNS and redirects the firm trusts; the vendor executes requests later. Tools cannot change this setting.

Webhook destinations in `fields_json` use an explicit set of destination aliases, validated by the same allowlist even inside nested objects and arrays. Unrelated fields such as `securityLevel` and `jurisdiction` pass unchanged.

## Testing

The test suite runs offline and needs no Filevine account: every Filevine API call is answered by an in-process fake session. It covers list limits and paging, path-identifier validation, destination URL and region checks, safe error messages and log privacy, credential file handling, the setup and verify commands, the stdio server, and the Streamable HTTP transport including the 2026-07-28 wire format, Host and Origin checks and stateless requests.

```bash
uv sync --locked
uv run --locked pytest -q
```

CI runs the suite on every push and pull request to `main`.

## License

MIT. See [LICENSE](LICENSE).
