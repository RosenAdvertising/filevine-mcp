"""Administrator-approved HTTPS destinations; no DNS or network side effects."""

import ipaddress
import os
import re
import socket
from urllib.parse import urlsplit


class UnsafeURL(ValueError):
    """Fixed reason codes; never include the supplied URL in errors."""


def _validate_literal_https(url: str) -> None:
    if not isinstance(url, str) or re.search(r"[\x00-\x20\x7f\\]", url):
        raise UnsafeURL("invalid_url")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise UnsafeURL("invalid_url") from None
    if parsed.scheme != "https":
        raise UnsafeURL("non_https_scheme")
    if not host:
        raise UnsafeURL("missing_hostname")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("userinfo")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeURL("invalid_port")
    if "%" in host or "{" in parsed.netloc or "}" in parsed.netloc:
        raise UnsafeURL("invalid_hostname")
    try:
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise UnsafeURL("invalid_hostname") from None
    if host in {
        "localhost",
        "localhost.localdomain",
        "local",
        "internal",
    } or host.endswith((".localhost", ".localhost.localdomain", ".local", ".internal")):
        raise UnsafeURL("reserved_hostname")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # inet_aton parses decimal integers, hex, octal and shortened IPv4
        # locally, without resolving DNS. Reject alternate notation entirely.
        try:
            socket.inet_aton(host)
        except OSError:
            pass
        else:
            raise UnsafeURL("private_address") from None
        # A numeric final label may be interpreted as IPv4 by URL parsers.
        if (
            re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", host.rsplit(".", 1)[-1])
            or len(host) > 253
            or "." not in host
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            )
        ):
            raise UnsafeURL("invalid_hostname") from None
        return
    address = getattr(address, "ipv4_mapped", None) or address
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise UnsafeURL("private_address")


DESTINATION_SETTING = "FILEVINE_ALLOWED_DESTINATION_HOSTS"


def _normalize_host(host: str) -> str:
    try:
        return host.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        raise UnsafeURL("invalid_hostname") from None


def validate_public_https(url: str) -> None:
    """Require a literal-safe URL and an administrator-approved hostname.

    Exact entries match only that host; a leading dot includes subdomains.
    No resolution or request is made here: administrators own the trust list.
    """
    _validate_literal_https(url)
    host = _normalize_host(urlsplit(url).hostname)
    message = (
        "Destination host is not approved; configure "
        + DESTINATION_SETTING
        + " with comma-separated trusted hostnames (or .domain for subdomains)."
    )
    entries = []
    for raw in os.environ.get(DESTINATION_SETTING, "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        subtree = raw.startswith(".")
        candidate = _normalize_host(raw[1:] if subtree else raw)
        # Entries are hosts, never URLs, userinfo, ports, paths or wildcards.
        if not candidate or any(c in candidate for c in "/@?#%*[]\\"):
            raise UnsafeURL(message)
        authority = "[" + candidate + "]" if ":" in candidate else candidate
        try:
            _validate_literal_https("https://" + authority)
        except UnsafeURL:
            raise UnsafeURL(message) from None
        entries.append((candidate, subtree))
    if not any(
        host == entry or (subtree and host.endswith("." + entry))
        for entry, subtree in entries
    ):
        raise UnsafeURL(message)
