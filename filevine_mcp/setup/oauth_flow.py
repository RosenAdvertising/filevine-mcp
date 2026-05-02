#!/usr/bin/env python3
"""Filevine MCP setup — client credentials configuration (no browser required)."""

import json
import os
import sys
import time
import requests
from pathlib import Path

CONFIG_DIR = Path.home() / ".filevine-mcp"

REGIONS = {
    "us": {
        "api": "https://api.filevineapp.com",
        "identity": "https://identity.filevineapp.com",
    },
    "ca": {
        "api": "https://api.filevineapp.ca",
        "identity": "https://identity.filevineapp.ca",
    },
    "cjis": {
        "api": "https://api.filevinegov.com",
        "identity": "https://identity.filevinegov.com",
    },
}


def prompt(label, default="", secret=False):
    suffix = f" [{default}]" if default else ""
    if secret:
        import getpass
        val = getpass.getpass(f"{label}{suffix}: ").strip()
    else:
        val = input(f"{label}{suffix}: ").strip()
    return val or default


def fetch_token(client_id, client_secret, identity_base):
    token_url = f"{identity_base}/connect/token"
    resp = requests.post(token_url, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "openid",
    })
    if resp.status_code == 200:
        return resp.json()
    raise RuntimeError(f"Token request failed ({resp.status_code}): {resp.text}")


def main():
    print("Filevine MCP Setup")
    print("==================")
    print("Filevine uses OAuth 2.0 client credentials — no browser required.")
    print()

    print("Region options: us, ca, cjis")
    region = prompt("Region", default="us").lower()
    if region not in REGIONS:
        print(f"Unknown region '{region}'. Defaulting to 'us'.")
        region = "us"

    region_cfg = REGIONS[region]
    identity_base = region_cfg["identity"]

    client_id = prompt("Client ID")
    client_secret = prompt("Client Secret", secret=True)
    org_id = prompt("Org ID (optional, press Enter to skip)", default="")

    print()
    print("Testing credentials...")
    try:
        tokens = fetch_token(client_id, client_secret, identity_base)
        expires_in = tokens.get("expires_in", 3600)
        tokens["expires_at"] = time.time() + expires_in

        print(f"✓ Token obtained. Expires in {expires_in}s.")
    except RuntimeError as e:
        print(f"✗ Failed: {e}")
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    env_file = CONFIG_DIR / ".env"
    env_content = f"""# Filevine MCP configuration
FILEVINE_CLIENT_ID={client_id}
FILEVINE_CLIENT_SECRET={client_secret}
FILEVINE_ORG_ID={org_id}
FILEVINE_REGION={region}
"""
    env_file.write_text(env_content)
    os.chmod(env_file, 0o600)

    token_file = CONFIG_DIR / "tokens.json"
    token_file.write_text(json.dumps(tokens, indent=2))
    os.chmod(token_file, 0o600)

    print()
    print(f"✓ Config saved to {CONFIG_DIR}")
    print()
    print("Add to your Claude Desktop config:")
    print(json.dumps({
        "mcpServers": {
            "filevine": {
                "command": "filevine-mcp"
            }
        }
    }, indent=2))


if __name__ == "__main__":
    main()
