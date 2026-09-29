#!/usr/bin/env python3
"""Verify Filevine MCP credentials by calling the /Users/Me endpoint."""

import sys

from filevine_mcp.client import FileVineClient, FilevineClientError


def main():
    print("Verifying Filevine MCP credentials...")
    try:
        client = FileVineClient()
        client.get_me()
        print("✓ Filevine credentials verified.")
    except FilevineClientError as exc:
        print(f"✗ Verification failed: {exc}")
        print("Run filevine-mcp-setup to update credentials or authorization.")
        sys.exit(1)
    except ValueError:
        print(
            "✗ Verification failed. Check the organization ID and stored tokens; run filevine-mcp-setup."
        )
        sys.exit(1)
    except Exception:
        print(
            "✗ Verification failed unexpectedly. Check configuration and network access."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
