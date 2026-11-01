"""Claude Code yönetilen (managed) ayarları: izin kuralları ve izin anahtarları (#65).

Claude Code belgesi (code.claude.com/docs/en/settings#settings-precedence,
permissions#managed-settings): öncelik managed > komut satırı > yerel > proje > kullanıcı.
Yönetilen dosya sistem dizinindedir ve kullanıcı ya da proje tarafından aşılamaz:

    macOS    /Library/Application Support/ClaudeCode/managed-settings.json
    Linux    /etc/claude-code/managed-settings.json
    Windows  C:/Program Files/ClaudeCode/managed-settings.json

Aynı dizindeki `managed-settings.d/*.json` parçaları alfabetik sırayla ana dosyanın üstüne
birleşir (dizi değerleri eklenir, öteki anahtarlarda sonraki kazanır).

`allowManagedPermissionRulesOnly: true` (yalnız managed dosyada geçerli) kullanıcı, proje ve
yerel ayarların allow/ask/deny kurallarını devre dışı bırakır; yalnız managed kurallar uygulanır.

Fusion yalnız okur; bu dosyalara hiçbir koşulda yazmaz. Testler gerçek sistem dizinine
dokunmasın diye `FUSION_CLAUDE_MANAGED_DIR` dizini ezer (talimat katmanıyla aynı değişken).
"""

from __future__ import annotations

import json
import os
import platform
from collections.abc import Mapping
from pathlib import Path

#: Yönetilen dizin (işletim sistemine göre); Claude Code ile aynı konumlar.
MANAGED_DIRS: dict[str, Path] = {
    "Darwin": Path("/Library/Application Support/ClaudeCode"),
    "Linux": Path("/etc/claude-code"),
    "Windows": Path("C:/Program Files/ClaudeCode"),
}
MANAGED_DIR_ENV = "FUSION_CLAUDE_MANAGED_DIR"
MANAGED_SETTINGS_NAME = "managed-settings.json"
MANAGED_DROPIN_DIR = "managed-settings.d"
#: Yalnız managed dosyada anlamlı anahtar.
MANAGED_RULES_ONLY_KEY = "allowManagedPermissionRulesOnly"


def managed_dir() -> Path | None:
    """Yönetilen ayar dizini; ortam değişkeni verilmişse o."""
    override = os.environ.get(MANAGED_DIR_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return MANAGED_DIRS.get(platform.system())


def managed_settings_files() -> tuple[Path, ...]:
    """Okuma sırasıyla yönetilen dosyalar: ana dosya, sonra `managed-settings.d/*.json`."""
    base = managed_dir()
    if base is None:
        return ()
    files: list[Path] = []
    main = base / MANAGED_SETTINGS_NAME
    if main.is_file():
        files.append(main)
    dropins = base / MANAGED_DROPIN_DIR
    try:
        parts = sorted(p for p in dropins.iterdir() if p.suffix == ".json" and p.is_file())
    except OSError:
        parts = []
    files.extend(parts)
    return tuple(files)


def managed_settings_data() -> Mapping[str, object]:
    """Yönetilen dosyaların birleşimi; dosya yoksa boş sözlük. Bozuk dosya atlanır."""
    merged: dict[str, object] = {}
    for path in managed_settings_files():
        data = _read(path)
        if data is not None:
            merged = _merge(merged, data)
    return merged


def managed_permission_rules_only() -> bool:
    """Managed `allowManagedPermissionRulesOnly: true` mu?"""
    data = managed_settings_data()
    value = data.get(MANAGED_RULES_ONLY_KEY)
    if value is None:
        permissions = data.get("permissions")
        if isinstance(permissions, Mapping):
            value = permissions.get(MANAGED_RULES_ONLY_KEY)
    return value is True


def _merge(base: Mapping[str, object], extra: Mapping[str, object]) -> dict[str, object]:
    """Yeni sözlük: diziler eklenir, iç sözlükler derin birleşir, ötekilerde `extra` kazanır."""
    result = dict(base)
    for key, value in extra.items():
        current = result.get(key)
        if isinstance(current, list) and isinstance(value, list):
            result[key] = [*current, *value]
        elif isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = _merge(current, value)
        else:
            result[key] = value
    return result


def _read(path: Path) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
