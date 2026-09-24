"""Where a provider's gateway lives, checked before a key is ever sent to it.

Every provider sends its key in an Authorization header, so a plain-http base URL pointing at a
public host would put that key on the wire in the clear. http stays allowed for a gateway on this
machine or on the private network — the documented FreeLLMAPI setup on host.docker.internal is
exactly that — and https is required for anything reachable from the internet.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})


def _is_local(host: str) -> bool:
    if host in LOCAL_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        return True
    # A single-label name is never a public host: it is a container or a machine on the LAN,
    # which is how the documented Compose setup reaches the gateway (http://freellmapi:3001/v1).
    if "." not in host and ":" not in host:
        return bool(host)
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        # A name, not an address: only the names above count as local.
        return False


def checked_base_url(variable: str, raw: str) -> str:
    """The base URL, or a RuntimeError naming the variable that has to change."""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"{variable} must use http or https")
    if parsed.username or parsed.password:
        raise RuntimeError(f"{variable} must not carry credentials in the URL")
    if parsed.query or parsed.fragment:
        raise RuntimeError(f"{variable} must not carry a query string or fragment")
    host = parsed.hostname or ""
    if parsed.scheme == "http" and not _is_local(host):
        raise RuntimeError(f"{variable} must use https outside this machine and the private network")
    return raw
