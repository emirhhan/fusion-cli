"""Komut satırı izin bayrakları (Claude Code ile birebir; #47, #49, #50, #70, #85).

    --permission-mode <kip>              default|manual|acceptEdits|plan|auto|dontAsk|
                                         bypassPermissions; settings `defaultMode`'u ezer
    --dangerously-skip-permissions       `--permission-mode bypassPermissions` ile eşdeğer
    --allow-dangerously-skip-permissions bypass'ı Shift+Tab döngüsüne ekler, başlatmaz
    --allowedTools / --allowed-tools     ALLOW kuralları (sorulmadan çalışır; kümeyi daraltmaz)
    --disallowedTools / --disallowed-tools  DENY kuralları; yalın ad aracı bağlamdan çıkarır,
                                         `Bash(rm *)` aracı açık bırakıp yalnız eşleşeni reddeder
    --tools                              modele sunulan araç kümesini daraltır

Başlangıç kipi önceliği: bayrak > `permissions.defaultMode` > yerleşik varsayılan
(`claude -p`/headless için `default`, auto kapalıysa `default`). Eski Fusion bayrağı
`--mode/-m` bir sürüm boyunca kullanımdan kalkmış takma addır.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

from ..config.permission_rules import PermissionDecision, PermissionRule, parse_rule
from ..config.permission_settings import (
    auto_mode_disabled,
    bypass_mode_disabled,
    default_mode_setting,
)
from ..engines.agent.approval import ApprovalMode, parse_mode

LEGACY_MODE_WARNING = (
    "uyarı: `--mode/-m` kullanımdan kalktı; Claude Code adıyla `--permission-mode` kullanın "
    "(ör. `--permission-mode acceptEdits`)."
)
BYPASS_DISABLED_WARNING = (
    "uyarı: bypassPermissions kipi `permissions.disableBypassPermissionsMode` ile kapalı; "
    "Manuel (default) kipte başlanıyor."
)
#: Eski anlam (`--allowed-tools read_file,list_dir` modele yalnız bu araçları sunardı).
LEGACY_ALLOWED_TOOLS_WARNING = (
    "uyarı: `--allowed-tools` artık Claude Code gibi allow kuralıdır (sorulmadan çalışır), araç "
    "kümesini daraltmaz; {adlar} gibi Fusion araç adları hiçbir kuralla eşleşmez. Araç kümesini "
    "daraltmak için `--tools` (ör. `--tools Read,Grep`), kural için Claude adları (`Read`, "
    "`Bash(git log *)`) kullanın."
)
_LEGACY_TOOL_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
_warned: set[str] = set()


def warn_once(key: str, text: str) -> None:
    """Uyarıyı süreç başına bir kez stderr'e yaz."""
    if key in _warned:
        return
    _warned.add(key)
    print(text, file=sys.stderr)


def split_entries(raw: Iterable[str] | None) -> tuple[str, ...]:
    """Bayrak değerleri: virgülle ya da tekrarla; parantez içindeki virgül bölünmez."""
    found: list[str] = []
    for chunk in raw or ():
        depth = 0
        current: list[str] = []
        for char in chunk:
            depth += {"(": 1, ")": -1}.get(char, 0)
            if char == "," and depth <= 0:
                found.append("".join(current))
                current = []
                continue
            current.append(char)
        found.append("".join(current))
    return tuple(entry.strip() for entry in found if entry.strip())


def cli_rules(
    allowed: Iterable[str] | None, disallowed: Iterable[str] | None
) -> tuple[PermissionRule, ...]:
    """`--allowedTools` → ALLOW, `--disallowedTools` → DENY kuralları (kaynak `cli`)."""
    rules: list[PermissionRule] = []
    for entries, decision in (
        (split_entries(allowed), PermissionDecision.ALLOW),
        (split_entries(disallowed), PermissionDecision.DENY),
    ):
        rules.extend(r for e in entries if (r := parse_rule(e, decision, source="cli")))
    return tuple(rules)


def warn_legacy_allowed_tools(allowed: Iterable[str] | None) -> None:
    """Eski Fusion adlı `--allowed-tools` kullanımını bir kez uyar (anlamı değişti, #47)."""
    legacy = [e for e in split_entries(allowed) if _LEGACY_TOOL_NAME.match(e)]
    if legacy:
        names = ", ".join(f"`{name}`" for name in legacy[:3])
        warn_once("legacy-allowed-tools", LEGACY_ALLOWED_TOOLS_WARNING.format(adlar=names))


def bare_denied_names(disallowed: Iterable[str] | None) -> frozenset[str]:
    """Bağlamdan çıkarılacak yalın adlar (`Edit`, `mcp__s__t`); parantezliler kalır."""
    return frozenset(e for e in split_entries(disallowed) if "(" not in e and "*" not in e)


def resolve_start_mode(
    *,
    flag: str | None,
    legacy: str | None,
    skip_permissions: bool,
    root: Path,
    headless: bool,
) -> ApprovalMode:
    """Oturumun başlangıç kipi: bayrak > defaultMode > yerleşik varsayılan."""
    if skip_permissions:
        chosen = ApprovalMode.BYPASS
    elif flag:
        chosen = parse_mode(flag)
    elif legacy:
        warn_once("legacy-mode", LEGACY_MODE_WARNING)
        chosen = parse_mode(legacy)
    else:
        setting = default_mode_setting(root)
        chosen = parse_mode(setting) if setting else _built_in_default(root, headless)
    return enforce_mode_limits(chosen, root)


def enforce_mode_limits(mode: ApprovalMode, root: Path) -> ApprovalMode:
    """Ayarla kapatılmış kipi Manuel'e indir (`disableAutoMode`, `disableBypassPermissionsMode`)."""
    if mode is ApprovalMode.AUTO and auto_mode_disabled(root):
        return ApprovalMode.SECURITY
    if mode is ApprovalMode.BYPASS and bypass_mode_disabled(root):
        warn_once("bypass-disabled", BYPASS_DISABLED_WARNING)
        return ApprovalMode.SECURITY
    return mode


def _built_in_default(root: Path, headless: bool) -> ApprovalMode:
    """Claude'un yerleşik başlangıç kipi her yüzeyde `default` (Manuel, #54, #70)."""
    del root, headless
    return ApprovalMode.SECURITY
