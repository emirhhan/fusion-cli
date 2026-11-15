"""Conservative recovery matching for turn followup suggestions.

Historical failures remain in ToolUse and the transcript. Only a later observed
success for the same request, or the same measured static preview file, clears
the suggestion to repair that failure.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import unquote, urlsplit


def _arguments(use: object) -> Mapping[str, object] | None:
    value = getattr(use, "arguments", None)
    return value if isinstance(value, Mapping) else None


def _same_request(failed: object, success: object) -> bool:
    name = getattr(failed, "name", None)
    if not isinstance(name, str) or name != getattr(success, "name", None):
        return False
    if getattr(failed, "environment", None) != getattr(success, "environment", None):
        return False
    left, right = _arguments(failed), _arguments(success)
    if left is None or right is None:
        return False
    target_field = {
        "read_file": "path",
        "write_file": "path",
        "edit_file": "path",
        "run_shell": "command",
        "web_fetch": "url",
        "browser_open": "url",
        "web_search": "query",
        "start_preview": "path",
    }.get(name)
    if (
        target_field is None
        or not isinstance(left.get(target_field), str)
        or not left[target_field]
    ):
        return False
    try:
        return json.dumps(dict(left), sort_keys=True, allow_nan=False) == json.dumps(
            dict(right), sort_keys=True, allow_nan=False
        )
    except (TypeError, ValueError):
        return False


def _decoded_path(raw: str) -> str | None:
    try:
        path = unquote(raw, errors="strict")
    except UnicodeError:
        return None
    if not path.startswith("/") or path.startswith("//") or "\x00" in path:
        return None
    if any(part in {".", ".."} for part in path.split("/")):
        return None
    return path


def _file_target(use: object) -> Path | None:
    args = _arguments(use)
    if args is None or set(args) != {"url"} or not isinstance(args["url"], str):
        return None
    try:
        url = urlsplit(args["url"])
        if url.scheme != "file" or url.netloc not in {"", "localhost"} or url.query or url.fragment:
            return None
        path = _decoded_path(url.path)
        return Path(path).resolve() if path else None
    except (ValueError, OSError, RuntimeError):
        return None


def _preview_target(use: object, root: Path) -> tuple[str, Path] | None:
    args = _arguments(use)
    if args is None or args.get("name") or not isinstance(args.get("path"), str):
        return None
    output = getattr(use, "output", "")
    if not isinstance(output, str):
        return None
    match = re.match(r"Önizleme çalışıyor: (\S+) \(static\)\.", output)
    if match is None:
        return None
    try:
        preview_root = Path(str(args["path"]))
        if not preview_root.is_absolute():
            preview_root = root / preview_root
        if preview_root.resolve() != root:
            return None
        url = urlsplit(match[1])
        if (
            url.scheme not in {"http", "https"}
            or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
        ):
            return None
        _ = url.port  # Reject malformed ports rather than inferring an origin.
        path = _decoded_path(url.path)
        if path is None:
            return None
        target = (root / path.lstrip("/")).resolve()
        return (match[1], target) if target.is_relative_to(root) else None
    except (ValueError, OSError, RuntimeError):
        return None


def unresolved_tool_failures(uses: Sequence[object], root: Path) -> tuple[str, ...]:
    """Match only later successes; another target's success is not recovery."""
    pending: list[tuple[int, object]] = []
    previews: list[tuple[int, str, Path, object]] = []
    root = root.resolve()
    for index, use in enumerate(uses):
        if not getattr(use, "ok", True):
            pending.append((index, use))
            continue
        if getattr(use, "name", None) == "start_preview":
            proof = _preview_target(use, root)
            if proof is not None:
                previews.append((index, *proof, getattr(use, "environment", None)))
        success_args = _arguments(use)
        browser_url = (
            success_args.get("url")
            if getattr(use, "name", None) == "browser_open"
            and success_args is not None
            and set(success_args) == {"url"}
            else None
        )
        retained: list[tuple[int, object]] = []
        for failed_index, failed in pending:
            recovered = _same_request(failed, use)
            if (
                not recovered
                and browser_url
                and getattr(failed, "name", None) == "browser_open"
                and getattr(failed, "environment", None) == getattr(use, "environment", None)
            ):
                file_target = _file_target(failed)
                recovered = file_target is not None and any(
                    failed_index < preview_index < index
                    and browser_url == url
                    and file_target == target
                    and preview_environment == getattr(failed, "environment", None)
                    for preview_index, url, target, preview_environment in previews
                )
            if not recovered:
                retained.append((failed_index, failed))
        pending = retained
    return tuple(dict.fromkeys(str(getattr(use, "name", "")) for _, use in pending))
