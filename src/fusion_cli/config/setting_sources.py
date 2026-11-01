"""`--setting-sources` — hangi ayar katmanlarının yükleneceği (#296, #301 `--restricted`).

Claude Code: `--setting-sources user,project,local` yalnız adı geçen kaynakları yükler;
yönetilen (managed) ayarlar ve `--settings` her zaman yüklenir. Fusion'da kaynaklar:

- `user`    → `~/.claude/settings.json` ve Fusion'ın kullanıcı dosyaları (`permissions.json`,
  `hooks.json`; Fusion'ın kullanıcı düzeyi karşılıkları),
- `project` → projenin `.claude/settings.json`'ı,
- `local`   → projenin `.claude/settings.local.json`'ı.

Liste süreç ortamında (`FUSION_SETTING_SOURCES`) tutulur: aynı süreçteki alt ajanlar ve bu
oturumdan başlatılan alt süreçler (Claude'daki gibi) aynı listeyi devralır. Değişken yoksa
bütün kaynaklar yüklenir; boş değer hiçbir kaynağın yüklenmediği anlamına gelir.
Kaynak süzme yalnız YÜKLEMEYİ daraltır: güven denetimi (`fusion trust`) aynen sürer.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

SETTING_SOURCES_ENV = "FUSION_SETTING_SOURCES"
SOURCE_USER = "user"
SOURCE_PROJECT = "project"
SOURCE_LOCAL = "local"
ALL_SOURCES = (SOURCE_USER, SOURCE_PROJECT, SOURCE_LOCAL)

#: İzin/kanca katman adı → Claude ayar kaynağı (`permission_rules`/`hooks` katman adları).
_LAYER_SOURCES = {
    "fusion": SOURCE_USER,
    "kullanici": SOURCE_USER,
    "proje": SOURCE_PROJECT,
    "yerel": SOURCE_LOCAL,
}


def active_sources() -> frozenset[str] | None:
    """Yüklenecek kaynaklar; `None` hepsi (değişken tanımsız)."""
    raw = os.environ.get(SETTING_SOURCES_ENV)
    if raw is None:
        return None
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def source_enabled(source: str) -> bool:
    """Bu Claude kaynağı (`user`/`project`/`local`) yüklenecek mi?"""
    active = active_sources()
    return active is None or source in active


def layer_enabled(layer_name: str) -> bool:
    """İzin ya da kanca katmanı yüklenecek mi? Bilinmeyen katman (ör. managed) hep yüklenir."""
    source = _LAYER_SOURCES.get(layer_name)
    return source is None or source_enabled(source)


def set_setting_sources(sources: Iterable[str] | None) -> None:
    """Bu süreç (ve çocukları) için kaynak listesini ayarla; `None` sınırı kaldırır."""
    if sources is None:
        os.environ.pop(SETTING_SOURCES_ENV, None)
        return
    os.environ[SETTING_SOURCES_ENV] = ",".join(sources)
