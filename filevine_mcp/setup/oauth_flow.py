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
from pathlib import Path

import requests

from filevine_mcp import credentials
from filevine_mcp.client import (
    REQUEST_TIMEOUT,
    FilevineClientError,
    _token_response,
)

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
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 200:
        return _token_response(resp)
    if resp.status_code == 401:
        raise FilevineClientError(
            "Filevine rejected the credentials (401). Check the client ID, secret, and PAT."
        )
    if resp.status_code == 403:
        raise FilevineClientError(
            "Filevine access denied: the connected account lacks permission for this action (or the authorization expired; re-run filevine-mcp-setup if so)."
        )
    raise FilevineClientError(
        f"Filevine token request failed with HTTP {resp.status_code}. Check credentials and region."
    )


def _main():
    print("Filevine MCP Setup")
    print("==================")
    print("Filevine uses Personal Access Token (PAT) authentication.")
    print()

    print("Region options: us, ca, cjis")
    try:
        region = prompt("Region", default="us").lower()
        client_id = prompt("Client ID")
        client_secret = prompt("Client Secret", secret=True)
        pat = prompt("Personal Access Token (PAT)", secret=True)
        org_id = prompt("Org ID (optional, press Enter to skip)", default="")
    except EOFError:
        print(
            "✗ Setup input ended early. Re-run filevine-mcp-setup and provide the requested values."
        )
        sys.exit(1)
    if region not in REGIONS:
        print("Unknown region. Defaulting to 'us'.")
        region = "us"

    region_cfg = REGIONS[region]
    identity_base = region_cfg["identity"]

    if not client_id or not client_secret or not pat:
        print(
            "✗ Client ID, Client Secret, and PAT are required. Re-run setup and provide all three."
        )
        sys.exit(1)

    print()
    print("Testing credentials...")
    try:
        tokens = fetch_token(client_id, client_secret, identity_base, pat)
        expires_in = tokens.get("expires_in", 3600)
        tokens["expires_at"] = time.time() + expires_in

        print(f"✓ Token obtained. Expires in {expires_in}s.")
    except FilevineClientError as e:
        print(f"✗ Failed: {e}")
        sys.exit(1)
    except requests.RequestException:
        print(
            "✗ Filevine authorization request lost its connection; the outcome is unknown. Check whether authorization completed before retrying setup."
        )
        sys.exit(1)

    backends = {
        "FILEVINE_CLIENT_ID": credentials.set_secret("FILEVINE_CLIENT_ID", client_id),
        "FILEVINE_CLIENT_SECRET": credentials.set_secret(
            "FILEVINE_CLIENT_SECRET", client_secret
        ),
        "FILEVINE_ORG_ID": credentials.set_secret("FILEVINE_ORG_ID", org_id),
        "FILEVINE_REGION": credentials.set_secret("FILEVINE_REGION", region),
        "FILEVINE_PAT": credentials.set_secret("FILEVINE_PAT", pat),
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    token_file = CONFIG_DIR / "tokens.json"

    def secure_open(path, flags):
        fd = os.open(path, flags, 0o600)
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        return fd

    with open(token_file, "w", opener=secure_open) as f:
        f.write(json.dumps(tokens, indent=2))
    os.chmod(token_file, 0o600)

    print()
    backend_set = set(backends.values())
    if backend_set == {"keyring"}:
        print(
            f"✓ Credentials saved to the OS keyring ({credentials.storage_backend()})."
        )
    elif backend_set == {"file"}:
        print(f"✓ Credentials saved to {credentials.ENV_FILE} (0600).")
    else:
        file_keys = ", ".join(key for key, saved in backends.items() if saved == "file")
        print(
            "✓ Credentials saved with mixed storage — "
            f"these fell back to {credentials.ENV_FILE} (0600): {file_keys}; "
            f"the rest are in the OS keyring ({credentials.storage_backend()})."
        )
    print(f"✓ Tokens saved to {token_file}")
    print()
    print("Add to your Claude Desktop config:")
    print(
        json.dumps({"mcpServers": {"filevine": {"command": "filevine-mcp"}}}, indent=2)
    )


def main():
    try:
        _main()
    except Exception:
        print("✗ Setup failed. Check configuration and retry filevine-mcp-setup.")
        sys.exit(1)


if __name__ == "__main__":
    main()
