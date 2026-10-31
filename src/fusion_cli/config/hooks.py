"""Kanca tanımlarını ayar dosyalarından yükleme (P-009) — Claude Code'un `hooks` bloğu.

Biçim (`~/.claude/settings.json` ile aynı; Fusion'ın kendi dosyası da bu şemadadır):

    {"hooks": {"PreToolUse": [{"matcher": "Bash",
                               "hooks": [{"type": "command", "command": "~/bin/denetle",
                                          "timeout": 30}]}]},
     "disableAllHooks": false}

Katmanlar (okuma sırası): Fusion kullanıcı dosyası (`<yapılandırma>/hooks.json`), Claude
kullanıcı ayarı (`~/.claude/settings.json`), proje `.claude/settings.json` ve
`.claude/settings.local.json`. Kanca KOD ÇALIŞTIRIR: proje içi iki dosyanın kancaları
yalnız `fusion trust` sonrası ve içerik o günden beri değişmediyse okunur (izin kurallarının
allow'u gibi; bkz. `trust.py`). `disableAllHooks: true` da yalnız güvenilen dosyadan okunur:
kullanıcının koruyucu (engelleyen) kancalarını kapatmak gevşetmedir. Ölçüldü (31 Ekim):
güvenilmeyen depodaki `{"disableAllHooks": true}` kullanıcının bütün kancalarını sessizce
kapatıyordu; artık yok sayılır ve listede uyarı olarak görünür.

Kapatma: `runtime.hooks_enabled: false` hepsini kapatır; `FUSION_HOOKS=off` ortam değişkeni
de (test ve acil durum için). `runtime.claude_hooks` (varsayılan false) yalnız
`~/.claude/settings.json`'ı yönetir: oradaki betikler (ECC vb.) Claude'un kendi durum
dosyalarına yazabilir, her araç çağrısına süreç gecikmesi ekler ve araç girdi/çıktısını
görür; bu yüzden açıkça seçilir. Kapalıyken kancaları listede gerekçesiyle görünür. Proje
dosyaları `fusion trust` ile açılır (bu anahtardan bağımsız).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.hooks.events import (
    CLAUDE_ONLY_EVENTS,
    COMMAND_HANDLER,
    HookCommand,
    HookSet,
    HookSkip,
    parse_event,
)
from .paths import user_config_dir
from .permission_rules import LAYER_FUSION, LAYER_LOCAL, LAYER_PROJECT, LAYER_USER
from .trust import (
    PROJECT_PERMISSIONS_PATH,
    PROJECT_SETTINGS_PATH,
    is_permissions_trusted,
    is_project_settings_trusted,
)

#: Fusion'ın kendi kanca dosyası (kullanıcıya ait; proje dışı).
USER_HOOKS_NAME = "hooks.json"
#: Claude Code'un kullanıcı düzeyi ayar dosyası (ev dizinine göreli).
CLAUDE_USER_SETTINGS = Path(".claude") / "settings.json"
#: Tek bir kancaya verilebilecek en uzun süre (Claude'un varsayılanı 600 sn).
MAX_HOOK_TIMEOUT_S = 600.0
#: Kancaları kapatan ortam değişkeni ve kapalı sayılan değerleri.
HOOKS_ENV = "FUSION_HOOKS"
_OFF_VALUES = frozenset({"0", "off", "false", "no", "kapali", "kapalı"})
#: Kanca sürecine verilen proje kökü değişkenleri (Claude betikleri `$CLAUDE_PROJECT_DIR` kullanır).
PROJECT_DIR_VARIABLES = ("FUSION_PROJECT_DIR", "CLAUDE_PROJECT_DIR")
#: Tüm kancaları kapatan dosya anahtarı (Claude Code ile aynı).
DISABLE_ALL_KEY = "disableAllHooks"

REASON_UNTRUSTED = "proje güvenilmiyor (fusion trust)"
REASON_CLAUDE_OFF = "Claude kullanıcı kancaları kapalı (runtime.claude_hooks: true ile aç)"
REASON_HANDLER = "tür desteklenmiyor: {kind} (yalnız command)"
REASON_EVENT = "Fusion bu olayı tetiklemiyor"
REASON_UNKNOWN_EVENT = "bilinmeyen olay"
REASON_EMPTY = "komut boş"


@dataclass(frozen=True, slots=True)
class HookLayer:
    """Bir kanca dosyası ve güven koşulu."""

    name: str
    path: Path
    requires_trust: bool = False
    #: Claude Code'un kullanıcı dosyası mı? (`runtime.claude_hooks: false` bunu atlar.)
    is_claude: bool = False


def hook_layers(root: Path, home: Path | None = None) -> tuple[HookLayer, ...]:
    """Okuma sırasıyla katmanlar: fusion → kullanıcı → proje → yerel."""
    base = home if home is not None else Path.home()
    return (
        HookLayer(LAYER_FUSION, user_config_dir() / USER_HOOKS_NAME),
        HookLayer(LAYER_USER, base / CLAUDE_USER_SETTINGS, is_claude=True),
        HookLayer(LAYER_PROJECT, root / PROJECT_SETTINGS_PATH, requires_trust=True),
        HookLayer(LAYER_LOCAL, root / PROJECT_PERMISSIONS_PATH, requires_trust=True),
    )


def user_hooks_file() -> Path:
    return user_config_dir() / USER_HOOKS_NAME


def hooks_disabled_by_environment() -> bool:
    """`FUSION_HOOKS=off` tanımlı mı? (Ortam yalnız config katmanında okunur.)"""
    return os.environ.get(HOOKS_ENV, "").strip().lower() in _OFF_VALUES


def hook_environment(root: Path) -> dict[str, str]:
    """Kanca sürecinin ortamı: Fusion'ınki + proje kökü değişkenleri."""
    return {**os.environ, **dict.fromkeys(PROJECT_DIR_VARIABLES, str(root))}


def load_hooks(
    root: Path,
    *,
    enabled: bool = True,
    include_claude: bool = False,
    default_timeout_s: float = 60.0,
    home: Path | None = None,
) -> HookSet:
    """Tüm katmanları oku. Bozuk dosya kanca AÇMAZ ve ötekileri düşürmez."""
    if not enabled:
        return HookSet(disabled_reason="runtime.hooks_enabled: false")
    if hooks_disabled_by_environment():
        return HookSet(disabled_reason=f"{HOOKS_ENV}=off")
    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    untrusted: list[str] = []
    ignored_disable: list[str] = []
    disabled: str | None = None
    for layer in hook_layers(root, home):
        data = _read_json(layer.path)
        if data is None:
            continue
        if layer.is_claude and not include_claude:
            found, _ = parse_hooks_block(
                data.get("hooks"),
                source=layer.name,
                path=layer.path,
                default_timeout_s=default_timeout_s,
            )
            skipped.extend(_as_skip(command, REASON_CLAUDE_OFF) for command in found)
            continue
        trusted = not layer.requires_trust or _is_trusted(layer, root)
        if data.get("disableAllHooks") is True:
            if not trusted:
                ignored_disable.append(layer.name)
            elif disabled is None:
                disabled = f"{DISABLE_ALL_KEY} ({layer.name}: {layer.path})"
        found, skips = parse_hooks_block(
            data.get("hooks"),
            source=layer.name,
            path=layer.path,
            default_timeout_s=default_timeout_s,
        )
        if not trusted:
            if found:
                untrusted.append(layer.name)
            skipped.extend(_as_skip(command, REASON_UNTRUSTED) for command in found)
            continue
        commands.extend(found)
        skipped.extend(skips)
    return HookSet(
        tuple(commands), tuple(skipped), disabled, tuple(untrusted), tuple(ignored_disable)
    )


def untrusted_hook_files(root: Path) -> tuple[str, ...]:
    """Güvenilmediği için kancaları çalışmayan proje dosyaları (köke göreli).

    Güven onayı (`fusion trust`, masaüstü şeridi) bunu söylemeli: güvenden sonra bu dosyaların
    kanca komutları her araç çağrısında kullanıcının yetkisiyle çalışır.
    """
    found: list[str] = []
    for layer in hook_layers(root):
        if not layer.requires_trust or _is_trusted(layer, root):
            continue
        data = _read_json(layer.path)
        block = data.get("hooks") if data is not None else None
        if isinstance(block, Mapping) and any(block.values()):
            found.append(layer.path.relative_to(root).as_posix())
    return tuple(found)


def parse_hooks_block(
    block: object, *, source: str, path: Path, default_timeout_s: float
) -> tuple[tuple[HookCommand, ...], tuple[HookSkip, ...]]:
    """`hooks` nesnesini komutlara çevir; çalıştırılamayan girdiler gerekçeli atlanır."""
    if not isinstance(block, Mapping):
        return (), ()
    commands: list[HookCommand] = []
    skipped: list[HookSkip] = []
    for event_name, groups in block.items():
        if not isinstance(groups, list):
            continue
        event = parse_event(str(event_name))
        for group in groups:
            if not isinstance(group, Mapping):
                continue
            matcher = group.get("matcher")
            matcher_text = matcher if isinstance(matcher, str) else ""
            handlers = group.get("hooks")
            for handler in handlers if isinstance(handlers, list) else ():
                if not isinstance(handler, Mapping):
                    continue
                kind = str(handler.get("type") or COMMAND_HANDLER)
                command = handler.get("command")
                detail = command if isinstance(command, str) else str(handler.get("url") or kind)
                reason = _skip_reason(str(event_name), event is None, kind, command)
                if reason is not None or event is None:
                    skipped.append(
                        HookSkip(
                            str(event_name), matcher_text, detail, reason or "", source, str(path)
                        )
                    )
                    continue
                commands.append(
                    HookCommand(
                        event,
                        matcher_text,
                        str(command).strip(),
                        _timeout(handler.get("timeout"), default_timeout_s),
                        source,
                        str(path),
                    )
                )
    return tuple(commands), tuple(skipped)


def _skip_reason(event_name: str, unknown: bool, kind: str, command: object) -> str | None:
    if unknown:
        return REASON_EVENT if event_name in CLAUDE_ONLY_EVENTS else REASON_UNKNOWN_EVENT
    if kind != COMMAND_HANDLER:
        return REASON_HANDLER.format(kind=kind)
    if not isinstance(command, str) or not command.strip():
        return REASON_EMPTY
    return None


def _timeout(raw: object, default: float) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float) or raw <= 0:
        return min(default, MAX_HOOK_TIMEOUT_S)
    return min(float(raw), MAX_HOOK_TIMEOUT_S)


def _as_skip(command: HookCommand, reason: str) -> HookSkip:
    return HookSkip(
        command.event.value, command.matcher, command.command, reason, command.source, command.path
    )


def _is_trusted(layer: HookLayer, root: Path) -> bool:
    if layer.name == LAYER_PROJECT:
        return is_project_settings_trusted(root)
    return is_permissions_trusted(root)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass(frozen=True, slots=True)
class HookRow:
    """Liste satırı (CLI, `/hooks`, masaüstü): olay · eşleştirici · komut · kaynak · durum."""

    event: str
    matcher: str
    command: str
    timeout_s: float | None
    source: str
    path: str
    #: Boş = etkin; doluysa neden çalışmadığı.
    skipped: str = ""


def hook_rows(hooks: HookSet) -> tuple[HookRow, ...]:
    """Etkin komutlar ve atlanan tanımlar, olay adına göre sıralı."""
    rows = [
        HookRow(c.event.value, c.matcher, c.command, c.timeout_s, c.source, c.path)
        for c in hooks.commands
    ]
    rows.extend(
        HookRow(s.event, s.matcher, s.detail, None, s.source, s.path, s.reason)
        for s in hooks.skipped
    )
    return tuple(sorted(rows, key=lambda row: (row.event, bool(row.skipped))))
