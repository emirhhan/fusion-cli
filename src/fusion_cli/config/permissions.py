"""Proje izin listesi — `.claude/settings.local.json` ile uyum.

Claude Code kullanıcıları onaysız çalışmasına izin verdikleri komutları bu dosyada
tutar. Fusion aynı listeyi okur: iki ayrı yerde izin yönetmek zorunda kalmazsın.

Dosya proje İÇİNDEDİR, yani indirilmiş bir depo `Bash(*)` taşıyabilir. Bu yüzden
liste ancak kullanıcı projeye `fusion trust` ile güvendiyse ve dosya o günden beri
değişmediyse yüklenir (`config/trust.py`; L2-02).

Dosya yoksa, bozuksa ya da beklenmedik biçimdeyse boş liste döner — izin listesi bir
kolaylıktır, okunamaması turu düşürmemelidir. Bilinmeyen bir biçimde "her şeye izin
var" varsaymak ise kabul edilemez; bu yüzden hata durumunda liste BOŞTUR.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .setting_sources import SOURCE_LOCAL, source_enabled
from .trust import PROJECT_PERMISSIONS_PATH, is_permissions_trusted

#: Claude Code'un proje-yerel izin dosyası.
SETTINGS_PATH = PROJECT_PERMISSIONS_PATH

#: `Bash(...)` sarmalı: yalnızca kabuk komutları Fusion'ın onay akışıyla ilgilidir.
_BASH_PREFIX = "Bash("


#: Kabuk bir komutu başka komutlara bölen/yerine koyan karakterler. Bunlardan biri
#: varsa ön ek izni uygulanmaz: `git status *` kalıbı `git status; rm -rf ~` ile
#: eşleşmemeli.
_SHELL_META = re.compile(r"[;&|<>`\n\r]|\$\(|\$\{")


def has_untrusted_permissions(root: Path) -> bool:
    """Projede izin dosyası var ama güvenilmediği için yok mu sayılıyor?"""
    return (root / SETTINGS_PATH).is_file() and not is_permissions_trusted(root)


def load_allowed_commands(root: Path) -> frozenset[str]:
    """İzin verilen kabuk komutlarını oku (yalnız güvenilen projede)."""
    path = root / SETTINGS_PATH
    if not source_enabled(SOURCE_LOCAL) or not is_permissions_trusted(root):
        return frozenset()
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
    olmayan bir kalıp asla kısmi eşleşmez; `<ön ek> *` ve eski `<ön ek>:*` yazımı
    SÖZCÜK SINIRI ister (`git status *` → `git statusfoo` değil); komutta kabuk
    meta karakteri (`;`, `&&`, `|`, `$()`, yeni satır…) varsa ön ek izni uygulanmaz.
    """
    target = command.strip()
    for pattern in allowed:
        if pattern.endswith("*"):
            if _prefix_matches(target, pattern):
                return True
        elif target == pattern:
            return True
    return False


def _prefix_matches(target: str, pattern: str) -> bool:
    if _SHELL_META.search(target):
        return False
    body = pattern[:-1]
    if body.endswith(":"):  # eski `Bash(npm run test:*)` yazımı
        body = body[:-1] + " "
    prefix = body.rstrip()
    if body and not body[-1].isspace():
        return target.startswith(prefix)  # `npm run test*`: açık ön ek, sınır istemez
    if not prefix:
        return True  # `*` tek başına
    # `<ön ek> *`: ön ek komutun TAM sözcükleri olmalı.
    return target == prefix or target.startswith(prefix + " ")
