"""Platform-specific secret file storage regression tests."""

import os
import stat
from pathlib import Path
from unittest.mock import Mock

import pytest

from filevine_mcp import private_file as storage
from filevine_mcp import credentials

write = storage.write_private_file


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize(
    "failure", [None, "fchmod", "missing", "ineffective", "replace"]
)
def test_posix_private_atomic_write(tmp_path, monkeypatch, existing, failure):
    target = tmp_path / "profile" / "secret"
    target.parent.mkdir()
    if existing:
        target.write_text("old")
        target.chmod(0o644)
    real_open, real_replace = os.open, os.replace
    modes, descriptors, replacements = [], [], []

    def observe_open(path, flags, mode=0o777):
        fd = real_open(path, flags, mode)
        modes.append((mode, stat.S_IMODE(os.fstat(fd).st_mode)))
        descriptors.append(fd)
        assert os.fstat(fd).st_size == 0
        return fd

    def replace(source, destination):
        assert destination == target
        assert source.parent == target.parent
        assert source.read_text() == "new"
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        assert target.read_text() == "old" if existing else not target.exists()
        replacements.append(source)
        if failure == "replace":
            raise PermissionError("replace denied")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "open", observe_open)
    monkeypatch.setattr(os, "replace", replace)
    if failure == "fchmod":
        monkeypatch.setattr(os, "fchmod", Mock(side_effect=PermissionError("denied")))
    elif failure == "missing":
        monkeypatch.delattr(os, "fchmod")
    elif failure == "ineffective":
        monkeypatch.setattr(
            os,
            "fchmod",
            lambda fd, mode: os.chmod(
                target.parent
                / next(p.name for p in target.parent.iterdir() if p != target),
                0o644,
            ),
        )
    with monkeypatch.context() as platform:
        platform.setattr(os, "name", "posix")
        if failure:
            with pytest.raises((OSError, AttributeError)):
                write(target, "new")
        else:
            write(target, "new")
    assert modes == [(0o600, 0o600)]
    assert (
        target.read_text() == ("old" if failure else "new")
        if existing or not failure
        else not target.exists()
    )
    assert list(target.parent.iterdir()) == ([target] if target.exists() else [])
    assert bool(replacements) == (failure in (None, "replace"))
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("fchmod", ["absent", "forbidden"])
@pytest.mark.parametrize("failure", [False, True])
def test_windows_inherited_atomic_write(
    tmp_path, monkeypatch, existing, fchmod, failure
):
    profile = tmp_path / "profile"
    profile.mkdir()
    target = profile / "secret"
    if existing:
        target.write_text("old")
    real_replace, real_open = os.replace, os.open
    replacements, modes = [], []
    forbidden = Mock(side_effect=AssertionError("fchmod must not run on Windows"))

    def replace(source, destination):
        assert destination == target
        assert source.parent == target.parent
        assert source.read_text() == "new"
        assert target.read_text() == "old" if existing else not target.exists()
        replacements.append(source)
        if failure:
            raise PermissionError("replace denied")
        return real_replace(source, destination)

    def observe_open(path, flags, mode=0o777):
        modes.append(mode)
        assert flags & os.O_EXCL
        return real_open(path, flags, mode)

    # Keep the host's concrete path class while simulating Windows in os.
    monkeypatch.setattr(storage, "Path", type(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: profile))
    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "open", observe_open)
    with monkeypatch.context() as platform:
        platform.setattr(os, "name", "nt")
        if fchmod == "absent":
            platform.delattr(os, "fchmod")
        else:
            platform.setattr(os, "fchmod", forbidden)
        if failure:
            with pytest.raises(PermissionError):
                write(target, "new")
        else:
            write(target, "new")
    forbidden.assert_not_called()
    assert modes == [0o666]
    assert len(replacements) == 1
    assert (
        target.read_text() == ("old" if failure else "new")
        if existing or not failure
        else not target.exists()
    )
    assert list(profile.iterdir()) == ([target] if target.exists() else [])


def test_windows_rejects_destination_outside_profile(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    target = tmp_path / "outside" / "secret"
    monkeypatch.setattr(storage, "Path", type(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: profile))
    with monkeypatch.context() as platform:
        platform.setattr(os, "name", "nt")
        platform.delattr(os, "fchmod")
        with pytest.raises(PermissionError, match="user profile"):
            write(target, "new")
    assert not target.parent.exists()


def test_windows_credentials_file_fallback(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    config = profile / ".filevine_mcp"
    target = config / ".env"
    monkeypatch.setattr(storage, "Path", type(tmp_path))
    monkeypatch.setattr(credentials, "Path", type(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: profile))
    if hasattr(credentials, "CONFIG_DIR"):
        monkeypatch.setattr(credentials, "CONFIG_DIR", config)
        monkeypatch.setattr(credentials, "ENV_FILE", target)
    else:
        monkeypatch.setattr(credentials, "env_file", lambda: target)
    with monkeypatch.context() as platform:
        platform.setattr(os, "name", "nt")
        platform.delattr(os, "fchmod")
        credentials._write_env_file({"TEST_VALUE": "synthetic"})
    assert target.read_text() == "TEST_VALUE=synthetic\n"


@pytest.mark.parametrize("platform_name", ["posix", "nt"])
@pytest.mark.parametrize("failure", [False, True])
def test_token_store_uses_platform_writer(
    tmp_path, monkeypatch, platform_name, failure
):
    import json

    from filevine_mcp import client

    profile = tmp_path / "profile"
    profile.mkdir()
    target = profile / "tokens.json"
    target.write_text('{"access_token": "old"}')
    monkeypatch.setattr(storage, "Path", type(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: profile))
    manager = object.__new__(client.TokenManager)
    manager.token_file = target
    save = manager.save
    forbidden = Mock(side_effect=PermissionError("denied"))
    original_replace = os.replace
    replacements = []

    def replace(source, destination):
        assert destination == target
        assert json.loads(target.read_text()) == {"access_token": "old"}
        replacements.append(source)
        if failure and platform_name == "nt":
            raise PermissionError("replace denied")
        return original_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    with monkeypatch.context() as platform:
        platform.setattr(os, "name", platform_name)
        if platform_name == "nt":
            platform.delattr(os, "fchmod")
        elif failure:
            platform.setattr(os, "fchmod", forbidden)
        if failure:
            with pytest.raises(PermissionError):
                save({"access_token": "new"})
        else:
            save({"access_token": "new"})
    assert json.loads(target.read_text()) == {
        "access_token": "old" if failure else "new"
    }
    assert bool(replacements) == (platform_name == "nt" or not failure)
    assert list(profile.iterdir()) == [target]
