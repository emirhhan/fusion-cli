"""Chrome yüklemesinde `Read(...)` izin kuralları (#437).

Claude Code (code.claude.com/docs/en/chrome, "Upload files to web pages"): Claude yalnız
oturumun okuyabildiği dosyayı yükleyebilir; `Read` erişimini reddeden izin kuralları o
dosyanın yüklenmesini de engeller. Fusion'da `chrome_action action=upload value=<yollar>`
çağrısı her yol için `Read(<yol>)` kuralına bakılarak değerlendirilir: `deny` reddeder,
`ask` sorar. `allow` kuralı yüklemeyi GENİŞLETMEZ (okuma izni yükleme onayı değildir).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from ..config.permission_rules import PermissionDecision, PermissionRule

UPLOAD_TOOL = "chrome_action"
READ_RULE = "Read"


def upload_paths(tool_name: str, args: Mapping[str, object]) -> tuple[str, ...]:
    """Yükleme çağrısının yolları; yükleme değilse boş."""
    if tool_name != UPLOAD_TOOL or args.get("action") != "upload":
        return ()
    value = args.get("value")
    if not isinstance(value, str):
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def upload_read_rule_matches(
    rule: PermissionRule,
    tool_name: str,
    args: Mapping[str, object],
    path_matches: Callable[[str, object, Path | None], bool],
    root: Path | None,
) -> bool:
    """Kısıtlayıcı `Read` kuralı yüklenen yollardan birine uyuyor mu?"""
    if rule.tool != READ_RULE or rule.decision is PermissionDecision.ALLOW:
        return False
    paths = upload_paths(tool_name, args)
    if not paths:
        return False
    if rule.specifier is None:
        return True
    return any(path_matches(rule.specifier, raw, root) for raw in paths)
