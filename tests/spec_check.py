#!/usr/bin/env python3
"""Offline guard for the MCP protocol revision supported by the lockfile."""

from __future__ import annotations

from mcp.types import LATEST_PROTOCOL_VERSION
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

EXPECTED_MCP_PROTOCOL_VERSION = "2026-07-28"


def check_mcp_revision() -> list[str]:
    """Return actionable errors when the installed SDK drifts from the pin."""
    errors: list[str] = []
    if LATEST_PROTOCOL_VERSION != EXPECTED_MCP_PROTOCOL_VERSION:
        errors.append(
            "installed MCP SDK targets "
            f"{LATEST_PROTOCOL_VERSION!r}, expected {EXPECTED_MCP_PROTOCOL_VERSION!r}"
        )
    if MODERN_PROTOCOL_VERSIONS != (EXPECTED_MCP_PROTOCOL_VERSION,):
        errors.append(
            "installed mcp-types modern revisions are "
            f"{MODERN_PROTOCOL_VERSIONS!r}, expected "
            f"({EXPECTED_MCP_PROTOCOL_VERSION!r},)"
        )
    return errors


def main() -> int:
    errors = check_mcp_revision()
    if errors:
        for error in errors:
            print(f"Spec check: FAIL: {error}")
        return 1
    print(f"Spec check: PASS ({EXPECTED_MCP_PROTOCOL_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
