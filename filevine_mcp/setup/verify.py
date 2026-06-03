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
        data = me if isinstance(me, dict) else {}
        full_name = data.get("fullName")
        if isinstance(full_name, str) and full_name.strip():
            name = full_name.strip()
        else:
            first = str(data.get("firstName", ""))
            last = str(data.get("lastName", ""))
            name = f"{first} {last}".strip()
        email = str(data.get("email", ""))
        print(f"✓ Authenticated as: {name} ({email})")
        print()
        print(json.dumps(me, indent=2))
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
