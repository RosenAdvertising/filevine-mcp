#!/usr/bin/env python3
"""Verify Filevine MCP credentials by calling the /Users/Me endpoint."""

import sys

from filevine_mcp.client import FileVineClient


def main():
    print("Verifying Filevine MCP credentials...")
    try:
        client = FileVineClient()
        client.get_me()
        print("✓ Filevine credentials verified.")
    except Exception:
        print("✗ Verification failed. Check credentials, region, and network access.")
        sys.exit(1)


if __name__ == "__main__":
    main()
