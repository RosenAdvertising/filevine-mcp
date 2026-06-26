#!/usr/bin/env python3
"""Filevine MCP setup — client credentials configuration (no browser required).

Credentials (Client ID, Client Secret, Org ID, Region) are stored securely via
the OS keyring (macOS Keychain / Windows Credential Manager / Linux Secret
Service), falling back to a 0600 ``.env`` file when no keyring backend is
available or ``FILEVINE_MCP_USE_KEYRING=0`` is set.
"""

import json
import os
import sys
import time
import requests
from pathlib import Path

from filevine_mcp import credentials

CONFIG_DIR = Path.home() / ".filevine-mcp"

REGIONS = {
    "us": {
        "api": "https://api.filevineapp.com",
        "identity": "https://identity.filevine.com",
    },
    "ca": {
        "api": "https://api.filevineapp.ca",
        "identity": "https://identity.filevine.ca",
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


def fetch_token(client_id, client_secret, identity_base, pat):
    token_url = f"{identity_base}/connect/token"
    resp = requests.post(
        token_url,
        data={
            "grant_type": "personal_access_token",
            "token": pat,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": (
                "fv.api.gateway.access tenant filevine.v2.api.* "
                "openid email fv.auth.tenant.read filevine.v2.webhooks"
            ),
        },
        timeout=5
    )
    if resp.status_code == 200:
        return resp.json()
    raise RuntimeError(f"Token request failed ({resp.status_code}): {resp.text}")


def main():
    print("Filevine MCP Setup")
    print("==================")
    print("Filevine uses Personal Access Token (PAT) authentication.")
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
    while True:
        pat = prompt("Personal Access Token (PAT)", secret=True)
        if pat:
            break
        print("PAT cannot be empty. Please enter a valid token.")
    org_id = prompt("Org ID (optional, press Enter to skip)", default="")

    print()
    print("Testing credentials...")
    try:
        tokens = fetch_token(client_id, client_secret, identity_base, pat)
        expires_in = tokens.get("expires_in", 3600)
        tokens["expires_at"] = time.time() + expires_in

        print(f"✓ Token obtained. Expires in {expires_in}s.")
    except RuntimeError as e:
        print(f"✗ Failed: {e}")
        sys.exit(1)

    backend = credentials.set_secret("FILEVINE_CLIENT_ID", client_id)
    credentials.set_secret("FILEVINE_CLIENT_SECRET", client_secret)
    credentials.set_secret("FILEVINE_ORG_ID", org_id)
    credentials.set_secret("FILEVINE_REGION", region)
    credentials.set_secret("FILEVINE_PAT", pat)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    token_file = CONFIG_DIR / "tokens.json"
    token_file.write_text(json.dumps(tokens, indent=2))
    os.chmod(token_file, 0o600)

    print()
    if backend == "keyring":
        print(
            f"✓ Credentials saved to the OS keyring ({credentials.storage_backend()})."
        )
    else:
        print(f"✓ Credentials saved to {credentials.ENV_FILE} (0600).")
    print(f"✓ Tokens saved to {token_file}")
    print()
    print("Add to your Claude Desktop config:")
    print(
        json.dumps({"mcpServers": {"filevine": {"command": "filevine-mcp"}}}, indent=2)
    )


if __name__ == "__main__":
    main()
