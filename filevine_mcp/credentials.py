#!/usr/bin/env python3
"""Pluggable credential storage for filevine-mcp.

Secrets (OAuth client ID, client secret, org ID, region) are stored in the
operating system's native secret store via the cross-platform ``keyring``
library:

  * macOS    -> Keychain
  * Windows  -> Credential Manager
  * Linux    -> Secret Service (GNOME Keyring / KWallet)

Storage order (read):  OS keyring  ->  process env  ->  ~/.filevine-mcp/.env file
Storage order (write):  OS keyring  (falls back to the 0600 .env file only when
                                     keyring is unavailable or disabled)

The file fallback keeps the historical chmod-0600 ``.env`` behaviour so the
server still works on headless hosts with no Secret Service backend, or when a
user opts out of keyring with ``FILEVINE_MCP_USE_KEYRING=0``.

Pluggable: keyring backends are user-selectable. Point at any backend (e.g.
``keyrings.cryptfile`` for an encrypted file, or a cloud backend) by setting the
standard ``PYTHON_KEYRING_BACKEND`` environment variable or a ``keyringrc.cfg``.
See https://github.com/jaraco/keyring#configuring for details.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# --- per-MCP configuration --------------------------------------------------
SERVICE_NAME = "filevine-mcp"
CONFIG_DIR = Path.home() / ".filevine-mcp"
ENV_FILE = CONFIG_DIR / ".env"
_USE_KEYRING_FLAG = "FILEVINE_MCP_USE_KEYRING"
# ---------------------------------------------------------------------------

# keyring is an optional-at-runtime dependency: import defensively so a missing
# or broken backend degrades to file storage instead of crashing the server.
# The module is held as ``Any`` because whether it exists and has a usable
# backend is a runtime fact (gated by ``_keyring_enabled()``), not something the
# type checker can prove — so attribute access on it is intentionally untyped.
keyring: Any
try:  # pragma: no cover - import guard
    import keyring as _keyring_mod
    from keyring.errors import KeyringError

    keyring = _keyring_mod
    _KEYRING_IMPORTED = True
except Exception:  # noqa: BLE001 - any import failure means "no keyring"
    keyring = None
    KeyringError = Exception
    _KEYRING_IMPORTED = False


def _keyring_enabled() -> bool:
    """True when keyring is importable, has a usable backend, and not opted out.

    Opt out with ``FILEVINE_MCP_USE_KEYRING=0`` (or false/no/off). A failing or
    "null" backend (common on headless Linux) is treated as disabled so we fall
    back to the file store rather than raising.
    """
    if not _KEYRING_IMPORTED:
        return False
    flag = os.environ.get(_USE_KEYRING_FLAG, "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    try:
        backend = keyring.get_keyring()
    except Exception:  # noqa: BLE001
        return False
    # keyring.backends.fail.Keyring / .null.Keyring are non-functional sentinels.
    cls = backend.__class__.__module__ + "." + backend.__class__.__name__
    if "fail." in cls or "null." in cls:
        return False
    return True


def _read_env_file() -> dict[str, str]:
    """Parse the 0600 ``.env`` fallback file into a dict (empty if absent)."""
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    values[key.strip()] = val.strip()
    return values


def _write_env_file(values: dict[str, str]) -> None:
    """Write the fallback ``.env`` file with 0600 perms in a 0700 dir."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_DIR.chmod(0o700)
    except OSError:
        pass
    lines = [f"{k}={v}" for k, v in values.items()]
    ENV_FILE.write_text("\n".join(lines) + ("\n" if lines else ""))
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass


def get_secret(key: str, default: str = "") -> str:
    """Return a credential by env-var name.

    Resolution order: OS keyring -> process environment -> ``.env`` file ->
    ``default``. An already-set process env var wins over the file (matching the
    historical ``os.environ.setdefault`` precedence) but keyring wins over all,
    so a rotated/most-recent secret is always preferred.
    """
    if _keyring_enabled():
        try:
            val = keyring.get_password(SERVICE_NAME, key)
            if val:
                return val
        except KeyringError:
            pass  # fall through to file/env
    # process env set by the parent shell takes next precedence
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    file_val = _read_env_file().get(key)
    if file_val:
        return file_val
    return default


def set_secret(key: str, value: str) -> str:
    """Persist a credential. Returns the backend used: ``"keyring"`` or ``"file"``.

    When keyring is active the secret goes ONLY to the OS store (never written to
    the plaintext file), so no clear-text copy is left on disk. When keyring is
    unavailable/disabled the secret is written to the 0600 ``.env`` fallback.
    """
    if _keyring_enabled():
        try:
            keyring.set_password(SERVICE_NAME, key, value)
            # If a legacy plaintext value exists in the file, scrub it so the
            # secret no longer lives on disk in clear text.
            existing = _read_env_file()
            if key in existing:
                existing.pop(key, None)
                _write_env_file(existing)
            return "keyring"
        except KeyringError:
            pass  # fall back to file
    existing = _read_env_file()
    existing[key] = value
    _write_env_file(existing)
    return "file"


def delete_secret(key: str) -> None:
    """Remove a credential from keyring (if present) and the file fallback."""
    if _keyring_enabled():
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except Exception:  # noqa: BLE001 - missing entry is fine
            pass
    existing = _read_env_file()
    if key in existing:
        existing.pop(key, None)
        _write_env_file(existing)


def load_into_environ(keys: list[str]) -> None:
    """Populate ``os.environ`` (via setdefault) for the given keys.

    Drop-in replacement for the old ``_load_env()`` so existing module-level
    ``os.environ.get(...)`` reads keep working, but values now resolve through
    keyring first. Only sets a key if not already present in the environment.
    """
    for key in keys:
        if os.environ.get(key):
            continue
        val = get_secret(key)
        if val:
            os.environ[key] = val


def storage_backend() -> str:
    """Human-readable name of the active backend, for setup/verify output."""
    if _keyring_enabled():
        try:
            return keyring.get_keyring().__class__.__name__
        except Exception:  # noqa: BLE001
            return "keyring"
    return f"file ({ENV_FILE})"
