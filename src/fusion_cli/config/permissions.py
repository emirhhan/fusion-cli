"""Proje izin listesi — `.claude/settings.local.json` ile uyum.

Claude Code kullanıcıları onaysız çalışmasına izin verdikleri komutları bu dosyada
tutar. Fusion aynı listeyi okur: iki ayrı yerde izin yönetmek zorunda kalmazsın.

Dosya yoksa, bozuksa ya da beklenmedik biçimdeyse boş liste döner — izin listesi bir
kolaylıktır, okunamaması turu düşürmemelidir. Bilinmeyen bir biçimde "her şeye izin
var" varsaymak ise kabul edilemez; bu yüzden hata durumunda liste BOŞTUR.
"""

from __future__ import annotations

import json
from pathlib import Path

#: Claude Code'un proje-yerel izin dosyası.
SETTINGS_PATH = Path(".claude") / "settings.local.json"

#: `Bash(...)` sarmalı: yalnızca kabuk komutları Fusion'ın onay akışıyla ilgilidir.
_BASH_PREFIX = "Bash("


def load_allowed_commands(root: Path) -> frozenset[str]:
    """İzin verilen kabuk komutlarını oku."""
    path = root / SETTINGS_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(data, dict):
        return frozenset()

    permissions = data.get("permissions")
    allow = permissions.get("allow") if isinstance(permissions, dict) else None
    if not isinstance(allow, list):
        return frozenset()
    return frozenset(
        _unwrap(entry) for entry in allow if isinstance(entry, str) and _is_bash(entry)
    )


def _is_bash(entry: str) -> bool:
    return entry.startswith(_BASH_PREFIX) and entry.endswith(")")


def _unwrap(entry: str) -> str:
    return entry[len(_BASH_PREFIX) : -1].strip()


def is_allowed(command: str, allowed: frozenset[str]) -> bool:
    """Komut izin listesindeki bir kalıba uyuyor mu?

    Kalıp sonda `*` taşıyorsa ön ek eşleşmesi yapılır (`git status *`), yoksa
    birebir eşleşme aranır. Ön ek eşleşmesi bilinçli olarak DAR tutulur: `*`
    olmayan bir kalıp asla kısmi eşleşmez.
    """
    target = command.strip()
    for pattern in allowed:
        if pattern.endswith("*"):
            if target.startswith(pattern[:-1].rstrip()):
                return True
        elif target == pattern:
            return True
    return False
