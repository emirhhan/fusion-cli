"""Match successful source reads to explicit requested URLs, not to arbitrary web activity."""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

_SOURCE_READERS = frozenset(
    {"web_fetch", "browser_open", "browser_tab_open", "site_crawl", "site_design", "clone_site"}
)


def _source_key(url: str) -> tuple[str, str, int | None, str, str] | None:
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        host = parsed.hostname.lower()
        port = parsed.port
        if port == (443 if parsed.scheme.lower() == "https" else 80):
            port = None
        return parsed.scheme.lower(), host, port, parsed.path or "/", parsed.query
    except ValueError:
        return None


def requested_sources_read(
    urls: Sequence[str], evidence: Sequence[tuple[str, dict[str, object], bool]]
) -> bool:
    """Prove reads of named pages; this does not claim semantic correctness or freshness.

    Evidence is admitted only after a successful real tool execution. Matching the
    requested URL (rather than a guessed final redirect) preserves legitimate redirects.
    Search queries, downloads and browser control/status calls do not prove a page read.
    """
    seen = {
        _source_key(url)
        for name, args, _ in evidence
        if name in _SOURCE_READERS and isinstance((url := args.get("url")), str)
    }
    seen.discard(None)
    return all((key := _source_key(url)) is not None and key in seen for url in urls)
