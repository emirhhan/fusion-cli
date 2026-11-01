"""Claude Code `settings.json` dosyalarındaki `sandbox` bölümü (#322, #369, #352).

Claude Code sandbox ayarlarını kendi ayar dosyalarından okur (settings-reference › sandbox):
`~/.claude/settings.json` (ya da `CLAUDE_CONFIG_DIR`), proje `.claude/settings.json` ve
`.claude/settings.local.json`, sonra `--settings` ve yönetilen (managed) ayarlar
(`claude_top_layers`, #321); sonraki öncekini ezer. Fusion aynı dosyaları aynı sırayla okur;
proje dosyaları yalnız güvenilen projede uygulanır (`trust`). Fusion YAML'ındaki `sandbox:`
bölümü bunların altında en düşük katmandır.

Birleştirme Claude'daki gibidir (sandboxing › "Path prefixes", "merged across scopes"): yol ve
alan adı listeleri katmanlar boyunca BİRLEŞİR, tekil değerlerde son katman kazanır.

Göreli yollar ayar dosyasının kapsamına göre çözülür (#369): proje ayarında proje kökü,
kullanıcı ayarında `~/.claude`. `/` mutlak, `~/` ev dizinidir.

`/sandbox` kip seçimi (aç/kapat, otomatik izin) Claude'daki gibi projenin
`.claude/settings.local.json` dosyasına yazılır (`write_local_sandbox`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields
from pathlib import Path

from ..core.errors import ConfigError
from . import trust
from .claude_home import claude_user_dir
from .claude_top_layers import top_layers
from .sandbox_claude_keys import (
    MANAGED_DOMAINS_ONLY_KEY,
    MANAGED_READ_ONLY_KEY,
    normalize_claude_sandbox,
)
from .sandbox_config import SandboxConfig

__all__ = [
    "ClaudeSandbox",
    "merge_sandbox_sections",
    "read_claude_sandbox",
    "with_claude_sandbox",
    "write_local_sandbox",
]

_LOG = logging.getLogger(__name__)

#: Katmanlar boyunca birleşen listeler (Claude: dizi ayarları kapsamlar arasında birleşir).
LIST_FIELDS = frozenset(
    {
        "allow_write",
        "deny_write",
        "deny_read",
        "allow_read",
        "allowed_domains",
        "denied_domains",
        "excluded_commands",
        "credential_env",
        "credential_files",
        "credential_mask",
    }
)
#: Proje ayar dosyalarından (`.claude/settings*.json`) OKUNMAYAN alanlar: Claude'da depo
#: yalıtımı gevşetemez, CA veremez, mask kaydı açamaz (settings-reference › sandbox).
PROJECT_IGNORED = frozenset(
    {
        "tls_terminate",
        "tls_ca_cert",
        "tls_ca_key",
        "credential_mask",
        "allow_plaintext_inject",
        "filesystem_disabled",
        "allow_nested_user_namespaces",
        "ripgrep_command",
        "ripgrep_args",
    }
)
#: Göreli yolu ayar dosyasının kapsamına göre çözülen alanlar.
PATH_FIELDS = ("allow_write", "deny_write", "deny_read", "allow_read", "credential_files")
_KNOWN = frozenset(item.name for item in fields(SandboxConfig))
_WARNED: set[str] = set()


@dataclass(frozen=True, slots=True)
class ClaudeSandbox:
    """Claude ayar dosyalarından birleşmiş sandbox bölümü (iç alan adlarıyla)."""

    section: dict[str, object]
    enabled: bool | None
    sources: tuple[Path, ...] = ()


def _sources(root: Path, home: Path | None) -> list[tuple[Path, Path]]:
    """(dosya, göreli yol tabanı) çiftleri; Claude sırasıyla, güvenilmeyen proje hariç."""
    user_dir = claude_user_dir(home)
    pairs = [(user_dir / "settings.json", user_dir)]
    if trust.is_project_settings_trusted(root):
        pairs.append((root / trust.PROJECT_SETTINGS_PATH, root))
    if trust.is_permissions_trusted(root):
        pairs.append((root / trust.PROJECT_PERMISSIONS_PATH, root))
    return pairs


def _load(path: Path) -> dict[str, object] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError):
        _LOG.warning("Claude ayar dosyası okunamadı; sandbox bölümü atlandı: %s", path)
        return None
    return raw if isinstance(raw, dict) else None


def _resolve(raw: object, base: Path) -> object:
    """`./x` ya da `x` → `<taban>/x`; `/`, `~`, `$HOME` olduğu gibi kalır."""
    if not isinstance(raw, str) or raw.startswith(("/", "~", "$HOME")):
        return raw
    relative = raw[2:] if raw.startswith("./") else raw
    return str(base / relative)


def _known_only(section: dict[str, object], path: Path) -> dict[str, object]:
    kept: dict[str, object] = {}
    for key, value in section.items():
        if key in _KNOWN:
            kept[key] = value
        elif key not in _WARNED:
            _WARNED.add(key)
            _LOG.warning("sandbox.%s Fusion'da henüz desteklenmiyor; yok sayıldı (%s)", key, path)
    return kept


def _candidates(
    root: Path, home: Path | None
) -> Iterator[tuple[Mapping[str, object], Path, Path, bool]]:
    """(içerik, kaynak, taban, managed mı) artan öncelikle: dosyalar, `--settings`, managed."""
    for path, base in _sources(root, home):
        data = _load(path)
        if data is not None:
            yield data, path, base, False
    for top in top_layers(root):
        yield top.data, top.source, top.base, top.name == "managed"


def _without_project_only(section: dict[str, object], path: Path) -> dict[str, object]:
    """Proje katmanında yok sayılan sandbox alanlarını (iç adlarla) çıkar; bir kez uyarır."""
    for key in sorted(PROJECT_IGNORED & {key for key, value in section.items() if value}):
        if f"proje:{key}" not in _WARNED:
            _WARNED.add(f"proje:{key}")
            _LOG.warning(
                "sandbox.%s proje ayarında yok sayıldı (Claude gibi yalnız kullanıcı, managed "
                "ya da --settings): %s",
                key,
                path,
            )
    return {key: value for key, value in section.items() if key not in PROJECT_IGNORED}


def _managed_flag(data: Mapping[str, object], group: str, key: str) -> bool:
    """Managed dosyasındaki `sandbox.<group>.<key>: true` kısıtı."""
    sandbox = data.get("sandbox")
    section = sandbox.get(group) if isinstance(sandbox, Mapping) else None
    return isinstance(section, Mapping) and section.get(key) is True


def _apply_managed_only(
    layers: list[tuple[dict[str, object], bool]], data: list[Mapping[str, object]]
) -> list[tuple[dict[str, object], bool]]:
    """`allowManagedReadPathsOnly` / `allowManagedDomainsOnly` (yalnız managed'da geçerli):
    managed dışı katmanların `allowRead` / `allowedDomains` listeleri yok sayılır."""
    managed = [item for item, (_, is_managed) in zip(data, layers, strict=True) if is_managed]
    dropped: set[str] = set()
    if any(_managed_flag(item, "filesystem", MANAGED_READ_ONLY_KEY) for item in managed):
        dropped.add("allow_read")
    domains_only = any(_managed_flag(item, "network", MANAGED_DOMAINS_ONLY_KEY) for item in managed)
    if domains_only:
        dropped.add("allowed_domains")
    result = [
        (
            section if is_managed else {k: v for k, v in section.items() if k not in dropped},
            is_managed,
        )
        for section, is_managed in layers
    ]
    if domains_only:
        # Claude: izinli olmayan alan adı sorulmadan engellenir.
        result.append(({"strict_allowlist": True}, True))
    return result


def _layer_from(
    data: Mapping[str, object], path: Path, base: Path
) -> tuple[dict[str, object], bool | None] | None:
    if "sandbox" not in data:
        return None
    try:
        section, enabled = normalize_claude_sandbox(data["sandbox"])
    except ConfigError as exc:
        _LOG.warning("Claude sandbox ayarı geçersiz; dosya atlandı (%s): %s", path, exc)
        return None
    section = _known_only(section, path)
    for name in PATH_FIELDS:
        values = section.get(name)
        if isinstance(values, list | tuple):
            section[name] = [_resolve(item, base) for item in values]
    return section, enabled


def merge_sandbox_sections(
    base: Mapping[str, object], overlay: Mapping[str, object]
) -> dict[str, object]:
    """İki iç adlı bölümü birleştir: listeler birleşir (sıra korunur), tekiller ezilir."""
    result = dict(base)
    for key, value in overlay.items():
        previous = result.get(key)
        if key in LIST_FIELDS and isinstance(value, list | tuple):
            earlier = list(previous) if isinstance(previous, list | tuple) else []
            result[key] = list(dict.fromkeys([*earlier, *value]))
        else:
            result[key] = value
    return result


def read_claude_sandbox(root: Path, *, home: Path | None = None) -> ClaudeSandbox:
    """Claude ayar dosyalarındaki `sandbox` bölümlerini sırayla birleştir."""
    layers: list[tuple[dict[str, object], bool]] = []
    raw: list[Mapping[str, object]] = []
    enabled: bool | None = None
    sources: list[Path] = []
    for data, path, base, is_managed in _candidates(root, home):
        layer = _layer_from(data, path, base)
        if layer is None:
            continue
        project = not is_managed and base == root and path.parent.name == ".claude"
        layers.append((_without_project_only(layer[0], path) if project else layer[0], is_managed))
        raw.append(data)
        if layer[1] is not None:
            enabled = layer[1]
        sources.append(path)
    section: dict[str, object] = {}
    for part, _ in _apply_managed_only(layers, raw):
        section = merge_sandbox_sections(section, part)
    return ClaudeSandbox(section, enabled, tuple(sources))


def with_claude_sandbox(
    data: Mapping[str, object], root: Path, *, home: Path | None = None
) -> dict[str, object]:
    """Birleşmiş Fusion yapılandırmasının üstüne Claude ayar dosyalarını uygula."""
    claude = read_claude_sandbox(root, home=home)
    result = dict(data)
    if claude.section:
        current = result.get("sandbox")
        base = current if isinstance(current, Mapping) else {}
        result["sandbox"] = merge_sandbox_sections(base, claude.section)
    if claude.enabled is not None:
        runtime = result.get("runtime")
        merged = dict(runtime) if isinstance(runtime, Mapping) else {}
        merged["shell_sandbox"] = "write_root" if claude.enabled else "off"
        result["runtime"] = merged
    return result


def write_local_sandbox(root: Path, values: Mapping[str, object]) -> Path:
    """`sandbox.<ad>` değerlerini projenin `.claude/settings.local.json`'ına yaz.

    Dosyadaki diğer ayarlar korunur; güven karması tazelenir ki Fusion'ın kendi yazdığı dosya
    bir sonraki yüklemede "güvenilmiyor" diye düşmesin (`permission_persist` ile aynı kural).
    """
    from .permission_rules import _write_json

    path = root / trust.PROJECT_PERMISSIONS_PATH
    data = _load(path) if path.is_file() else {}
    if data is None:
        raise ConfigError(f"Ayar dosyası okunamadı ya da JSON değil: {path}")
    section = data.get("sandbox")
    sandbox = dict(section) if isinstance(section, dict) else {}
    sandbox.update(values)
    _write_json(path, {**data, "sandbox": sandbox})
    trust.record_permissions_digest(root)
    return path
