"""Distinguish explicit URL schemes from bare host/port tool input."""

from __future__ import annotations

import re

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_HOST_PORT = re.compile(r"^[^:/?#\s]+:\d+(?=[/?#]|$)")


def has_explicit_scheme(raw: str) -> bool:
    """Keep protocols intact for policy checks; a bare host:port is not a scheme.

    Numeric port syntax is ambiguous with opaque URI payloads. Preserve explicit
    HTTP(S) and file schemes even there; other bare host:port input retains the
    existing HTTPS completion behavior. Bracketed IPv6 never matches _SCHEME.
    """
    match = _SCHEME.match(raw)
    if match is None:
        return False
    scheme = match.group()[:-1].lower()
    return (
        raw[match.end() :].startswith("//")
        or scheme in {"http", "https", "file"}
        or _HOST_PORT.match(raw) is None
    )
