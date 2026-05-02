#!/usr/bin/env python3
"""Verify Filevine MCP credentials by calling the /Users/Me endpoint."""

import json
import sys
from filevine_mcp.client import FileVineClient


def main():
    print("Verifying Filevine MCP credentials...")
    try:
        client = FileVineClient()
        me = client.get_me()
        name = me.get("fullName") or me.get("firstName", "") + " " + me.get("lastName", "")
        email = me.get("email", "")
        print(f"✓ Authenticated as: {name.strip()} ({email})")
        print()
        print(json.dumps(me, indent=2))
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
