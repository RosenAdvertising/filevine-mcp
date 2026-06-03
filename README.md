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

This prompts for your Client ID, Client Secret, Org ID, and region, then tests the credentials and saves them to `~/.filevine-mcp/`.

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

## Authentication Notes

Filevine uses OAuth 2.0 **client credentials** flow — no browser authorization required. Tokens are fetched automatically and refreshed when they expire. Three regions are supported with separate API and identity hosts:

| Region | API Host            | Identity Host            |
| ------ | ------------------- | ------------------------ |
| us     | api.filevineapp.com | identity.filevineapp.com |
| ca     | api.filevineapp.ca  | identity.filevineapp.ca  |
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
