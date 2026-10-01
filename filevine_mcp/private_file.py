"""Atomic private-file writes; permissions are established before any secret."""

import os
import secrets
import stat
from pathlib import Path


def write_private_file(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(16) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        # Fail closed before writing, including when tightening mode fails.
        if not hasattr(os, "fchmod"):
            raise PermissionError("Private file permissions could not be established.")
        os.fchmod(fd, 0o600)
        if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
            raise PermissionError("Private file permissions could not be established.")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = None
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if fd is not None:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()
