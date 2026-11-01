"""Kanca tanımlarını ayar dosyalarından yükleme (P-009) — Claude Code'un `hooks` bloğu.

Biçim (`~/.claude/settings.json` ile aynı):

    {"hooks": {"PreToolUse": [{"matcher": "Bash",
                               "hooks": [{"type": "command", "command": "~/bin/denetle",
                                          "timeout": 30}]}]},
     "disableAllHooks": false}

Katmanlar (okuma sırası, sonraki öncelikli): Fusion'ın eski kullanıcı dosyası
(`<yapılandırma>/hooks.json`, kullanımdan kalktı: okunur ve bir kez uyarılır), Claude
kullanıcı ayarı (`~/.claude/settings.json`, Claude gibi her zaman birleştirilir), proje
`.claude/settings.json`, `.claude/settings.local.json` ve yönetilen (managed) ayar. Proje
dosyalarının kancaları KOD ÇALIŞTIRIR: etkileşimli oturumda `fusion trust` sonrası (içerik o
günden beri değişmediyse) okunur; `-p`/SDK (etkileşimsiz) oturumda klasör güvenilir sayılır
(Claude Code ile aynı — güvenlik davranışı: depo kancaları `-p`'de çalışır).

`disableAllHooks` öncelik sırasından sonra kalan değerdir: projedeki `false` kullanıcıdaki
`true`'yu geçersiz kılar; yönetilen kancaları yalnız yönetilen düzeydeki değer kapatır.
`allowManagedHooksOnly: true` (yönetilen ayarda) yalnız yönetilen kancaları çalıştırır.
`allowedHttpHookUrls` tanımlıysa http kancası yalnız birleşik listedeki adrese gider;
`httpHookAllowedEnvVars` başlıklara yerleştirilebilecek ortam adlarını daraltır.

Fusion'a özgü kapatma anahtarları: `runtime.hooks_enabled: false`, `FUSION_HOOKS=off`;
`runtime.claude_hooks: false` `~/.claude/settings.json`'ı atlar (varsayılan true).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from ..core.hooks.events import HTTP_HANDLER, HookCommand, HookSet, HookSkip
from .hook_parse import (
    DEFAULT_HOOK_TIMEOUT_S,
    MAX_HOOK_TIMEOUT_S,
    REASON_EMPTY,
    REASON_EVENT,
    REASON_HANDLER,
    REASON_MCP,
    REASON_UNKNOWN_EVENT,
    REASON_URL,
    parse_hooks_block,
)
from .hook_policy import (
    REASON_HTTP_URL,
    REASON_MANAGED_ONLY,
    as_skip,
    http_rejection,
    narrow_env,
    policy_filter,
)
from .paths import user_config_dir
from .permission_rules import LAYER_FUSION, LAYER_LOCAL, LAYER_PROJECT, LAYER_USER
from .plugin_hooks import plugin_hooks
from .trust import (
    PROJECT_PERMISSIONS_PATH,
    PROJECT_SETTINGS_PATH,
    is_permissions_trusted,
    is_project_settings_trusted,
)

__all__ = [
    "DEFAULT_HOOK_TIMEOUT_S",
    "MAX_HOOK_TIMEOUT_S",
    "REASON_EMPTY",
    "REASON_EVENT",
    "REASON_HANDLER",
    "REASON_HTTP_URL",
    "REASON_MANAGED_ONLY",
    "REASON_MCP",
    "REASON_UNKNOWN_EVENT",
    "REASON_URL",
    "parse_hooks_block",
    "policy_filter",
]

#: Fusion'ın eski kanca dosyası (kullanımdan kalktı; `~/.claude/settings.json` kullanın).
USER_HOOKS_NAME = "hooks.json"
#: Claude Code'un kullanıcı düzeyi ayar dosyası (ev dizinine göreli).
CLAUDE_USER_SETTINGS = Path(".claude") / "settings.json"
#: Yönetilen (managed) katmanın adı.
LAYER_MANAGED = "yonetilen"
#: Kancaları kapatan ortam değişkeni ve kapalı sayılan değerleri.
HOOKS_ENV = "FUSION_HOOKS"
_OFF_VALUES = frozenset({"0", "off", "false", "no", "kapali", "kapalı"})
#: Kanca sürecine verilen proje kökü değişkenleri (Claude betikleri `$CLAUDE_PROJECT_DIR` kullanır).
PROJECT_DIR_VARIABLES = ("FUSION_PROJECT_DIR", "CLAUDE_PROJECT_DIR")
#: Tüm kancaları kapatan dosya anahtarı (Claude Code ile aynı).
DISABLE_ALL_KEY = "disableAllHooks"
MANAGED_ONLY_KEY = "allowManagedHooksOnly"
HTTP_URLS_KEY = "allowedHttpHookUrls"
HTTP_ENV_KEY = "httpHookAllowedEnvVars"
#: Stop sürdürme tavanı (Claude: art arda 8) ve değiştiren ortam değişkeni.
STOP_BLOCK_CAP_ENV = "CLAUDE_CODE_STOP_HOOK_BLOCK_CAP"
DEFAULT_STOP_BLOCK_CAP = 8
#: SessionEnd toplam bütçesi (Claude: 1,5 sn; en çok 60 sn) ve ortam değişkeni (ms).
SESSIONEND_TIMEOUT_ENV = "CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS"
SESSIONEND_BUDGET_S = 1.5
SESSIONEND_MAX_S = 60.0

REASON_UNTRUSTED = "proje güvenilmiyor (fusion trust)"
REASON_CLAUDE_OFF = "Claude kullanıcı kancaları kapalı (runtime.claude_hooks: false)"
NOTICE_FUSION_FILE = (
    "{path} kullanımdan kalktı; kancaları ~/.claude/settings.json `hooks` bloğuna taşıyın "
    "(bu sürümde hâlâ okunuyor)."
)


@dataclass(frozen=True, slots=True)
class HookLayer:
    """Bir kanca dosyası ve güven koşulu."""

    name: str
    path: Path
    requires_trust: bool = False
    #: Claude Code'un kullanıcı dosyası mı? (`runtime.claude_hooks: false` bunu atlar.)
    is_claude: bool = False
    is_managed: bool = False


#: Platforma göre Claude Code'un yönetilen ayar dosyası.
_MANAGED_PATHS = {
    "darwin": Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
    "win32": Path("C:/Program Files/ClaudeCode/managed-settings.json"),
}


def managed_settings_file() -> Path:
    """Claude Code'un yönetilen ayar dosyası (platforma göre)."""
    return _MANAGED_PATHS.get(sys.platform, Path("/etc/claude-code/managed-settings.json"))


def hook_layers(root: Path, home: Path | None = None) -> tuple[HookLayer, ...]:
    """Okuma sırasıyla katmanlar: fusion → kullanıcı → proje → yerel → yönetilen."""
    base = home if home is not None else Path.home()
    return (
        HookLayer(LAYER_FUSION, user_config_dir() / USER_HOOKS_NAME),
        HookLayer(LAYER_USER, base / CLAUDE_USER_SETTINGS, is_claude=True),
        HookLayer(LAYER_PROJECT, root / PROJECT_SETTINGS_PATH, requires_trust=True),
        HookLayer(LAYER_LOCAL, root / PROJECT_PERMISSIONS_PATH, requires_trust=True),
        HookLayer(LAYER_MANAGED, managed_settings_file(), is_managed=True),
    )


def user_hooks_file() -> Path:
    return user_config_dir() / USER_HOOKS_NAME


def hooks_disabled_by_environment() -> bool:
    """`FUSION_HOOKS=off` tanımlı mı? (Ortam yalnız config katmanında okunur.)"""
    return os.environ.get(HOOKS_ENV, "").strip().lower() in _OFF_VALUES


def stop_hook_block_cap() -> int:
    """Art arda Stop sürdürme tavanı (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`, varsayılan 8)."""
    raw = os.environ.get(STOP_BLOCK_CAP_ENV, "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else DEFAULT_STOP_BLOCK_CAP


def sessionend_budget_s(longest_explicit_s: float = 0.0) -> float:
    """SessionEnd kancalarının ortak bütçesi (Claude kuralı)."""
    raw = os.environ.get(SESSIONEND_TIMEOUT_ENV, "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw) / 1000
    return min(max(SESSIONEND_BUDGET_S, longest_explicit_s), SESSIONEND_MAX_S)


def explicit_sessionend_timeout_s() -> float | None:
    """Ortam değişkeni yazılıysa süresiz SessionEnd kancasının süresi de odur."""
    raw = os.environ.get(SESSIONEND_TIMEOUT_ENV, "").strip()
    return int(raw) / 1000 if raw.isdigit() and int(raw) > 0 else None


def hook_environment(
    root: Path, hidden: Collection[str] = (), extra: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Kanca sürecinin ortamı: Fusion'ınki (gizli adlar ve OTEL_* hariç) + proje değişkenleri.

    `hidden` MCP sırlarının adlarıdır (`run_shell` de çıkarır): çıkış 2'de stderr modele
    gider; `env` yazdıran bir betik sırrı modele sızdırmasın. `root` oturumun BAŞLADIĞI
    proje köküdür (worktree'de sabit, Claude `CLAUDE_PROJECT_DIR` gibi).
    """
    base = {
        name: value
        for name, value in os.environ.items()
        if name not in hidden and not name.startswith("OTEL_")
    }
    return {**base, **dict.fromkeys(PROJECT_DIR_VARIABLES, str(root)), **(extra or {})}


@dataclass(slots=True)
class _Collected:
    commands: list[HookCommand]
    skipped: list[HookSkip]
    untrusted: list[str]
    ignored_disable: list[str]
    notices: list[str]
    disable: tuple[bool, str] | None = None
    managed_disable: bool = False
    managed_only: bool = False
    http_urls: list[str] | None = None
    http_env: list[str] | None = None


def load_hooks(
    root: Path,
    *,
    enabled: bool = True,
    include_claude: bool = True,
    default_timeout_s: float = DEFAULT_HOOK_TIMEOUT_S,
    home: Path | None = None,
    interactive: bool = True,
    include_plugins: bool = True,
    pinned: Mapping[Path, Mapping[str, object] | None] | None = None,
) -> HookSet:
    """Tüm katmanları ve etkin eklentilerin kancalarını oku.

    Bozuk dosya kanca AÇMAZ ve ötekileri düşürmez. `pinned`: `ConfigChange`'in engellediği
    dosyalar → engelden önceki içerik (`None` = dosya yoktu); diskteki yeni hali okunmaz.
    """
    if not enabled:
        return HookSet(disabled_reason="runtime.hooks_enabled: false")
    if hooks_disabled_by_environment():
        return HookSet(disabled_reason=f"{HOOKS_ENV}=off")
    found = _Collected([], [], [], [], [])
    for layer in hook_layers(root, home):
        data = (
            pinned[layer.path]
            if pinned and layer.path in pinned
            else read_settings_json(layer.path)
        )
        if data is not None:
            _read_layer(found, layer, data, root, include_claude, default_timeout_s, interactive)
    if include_plugins:
        plugin_commands, plugin_skips = plugin_hooks(default_timeout_s)
        found.commands.extend(plugin_commands)
        found.skipped.extend(plugin_skips)
    return _finish(found)


def _read_layer(
    found: _Collected,
    layer: HookLayer,
    data: Mapping[str, object],
    root: Path,
    include_claude: bool,
    default_timeout_s: float,
    interactive: bool,
) -> None:
    commands, skips = parse_hooks_block(
        data.get("hooks", {}),
        source=layer.name,
        path=layer.path,
        default_timeout_s=default_timeout_s,
    )
    if layer.is_claude and not include_claude:
        found.skipped.extend(as_skip(command, REASON_CLAUDE_OFF) for command in commands)
        return
    trusted = not layer.requires_trust or not interactive or _is_trusted(layer, root)
    disable = data.get(DISABLE_ALL_KEY)
    if isinstance(disable, bool):
        if not trusted:
            if disable:
                found.ignored_disable.append(layer.name)
        elif layer.is_managed:
            found.managed_disable = disable
        else:
            found.disable = (disable, f"{DISABLE_ALL_KEY} ({layer.name}: {layer.path})")
    if not trusted:
        if commands:
            found.untrusted.append(layer.name)
        found.skipped.extend(as_skip(command, REASON_UNTRUSTED) for command in commands)
        return
    _read_http_policy(found, data)
    if layer.is_managed:
        found.managed_only = data.get(MANAGED_ONLY_KEY) is True
    if layer.name == LAYER_FUSION and commands:
        found.notices.append(NOTICE_FUSION_FILE.format(path=layer.path))
    found.commands.extend(commands)
    found.skipped.extend(skips)


def _read_http_policy(found: _Collected, data: Mapping[str, object]) -> None:
    urls = data.get(HTTP_URLS_KEY)
    if isinstance(urls, list):
        found.http_urls = [*(found.http_urls or []), *(u for u in urls if isinstance(u, str))]
    names = data.get(HTTP_ENV_KEY)
    if isinstance(names, list):
        found.http_env = [*(found.http_env or []), *(n for n in names if isinstance(n, str))]


def _finish(found: _Collected) -> HookSet:
    commands: list[HookCommand] = []
    skipped = list(found.skipped)
    user_disabled = found.disable is not None and found.disable[0]
    has_managed = any(command.source == LAYER_MANAGED for command in found.commands)
    for command in found.commands:
        managed = command.source == LAYER_MANAGED
        if found.managed_only and not managed:
            skipped.append(as_skip(command, REASON_MANAGED_ONLY))
            continue
        if user_disabled and has_managed and not managed:
            # Yönetilen kancaları kullanıcı/proje düzeyindeki disableAllHooks kapatamaz.
            skipped.append(as_skip(command, DISABLE_ALL_KEY))
            continue
        reason = http_rejection(command, found.http_urls)
        if reason is not None:
            skipped.append(as_skip(command, reason))
            continue
        commands.append(narrow_env(command, found.http_env))
    disabled = None
    if found.managed_disable:
        disabled = f"{DISABLE_ALL_KEY} ({LAYER_MANAGED})"
    elif user_disabled and not has_managed and found.disable is not None:
        disabled = found.disable[1]
    return HookSet(
        tuple(commands),
        tuple(skipped),
        disabled,
        tuple(found.untrusted),
        tuple(found.ignored_disable),
        tuple(found.notices),
        http_urls=None if found.http_urls is None else tuple(found.http_urls),
        http_env=None if found.http_env is None else tuple(found.http_env),
        managed_only=found.managed_only,
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
        data = read_settings_json(layer.path)
        block = data.get("hooks") if data is not None else None
        if isinstance(block, Mapping) and any(block.values()):
            found.append(layer.path.relative_to(root).as_posix())
    return tuple(found)


def _is_trusted(layer: HookLayer, root: Path) -> bool:
    if layer.name == LAYER_PROJECT:
        return is_project_settings_trusted(root)
    return is_permissions_trusted(root)


def read_settings_json(path: Path) -> dict[str, object] | None:
    """Ayar dosyasının nesnesi; yoksa, bozuksa ya da nesne değilse `None`."""
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


def _shown(command: HookCommand) -> str:
    return f"POST {command.command}" if command.handler == HTTP_HANDLER else command.command


def hook_rows(hooks: HookSet) -> tuple[HookRow, ...]:
    """Etkin komutlar ve atlanan tanımlar, olay adına göre sıralı."""
    rows = [
        HookRow(c.event.value, c.matcher, _shown(c), c.timeout_s, c.source, c.path)
        for c in hooks.commands
    ]
    rows.extend(
        HookRow(s.event, s.matcher, s.detail, None, s.source, s.path, s.reason)
        for s in hooks.skipped
    )
    return tuple(sorted(rows, key=lambda row: (row.event, bool(row.skipped))))
