"""`proje.dosya_ara`: `@` ile dosya anmanın veri kaynağı.

Arayüz her tuş vuruşunda sorar; bu yüzden iki şey önemli: liste TAZE olmalı
(agent'ın az önce yazdığı dosya anında görünsün) ama her istekte diskin
taranması gerekmez. Dosya listesi kısa ömürlü bir önbellekte tutulur, sorgu
eşleştirmesi ise her zaman yeniden koşar — eşleştirme saf ve ucuzdur
(`core/file_match.py`).

Katman yönü: `appserver → core`. Eşleştirme ve dosya listesi `core`'da durur,
burada yalnız RPC sözleşmesi ve önbellek vardır.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..core.clock import SystemClock
from ..core.file_match import match_files
from ..core.project_files import project_files
from ..core.protocols import Clock

__all__ = ["FileSearchIndex", "search_project_files"]

#: Dosya listesinin tazelik ömrü (saniye).
#
# Ölçüldü: liste üretimi bu depoda 48 ms. Her tuş vuruşunda yeniden üretmek
# yazarken hissedilir bir gecikme yaratır; çok uzun tutmak ise agent'ın az önce
# oluşturduğu dosyayı listede göstermez. İki saniye, yazma hızının üstünde ama
# bir turun altında kalır.
CACHE_TTL_SECONDS = 2.0

#: Tek istekte dönen en fazla sonuç. Açılır liste bundan fazlasını göstermiyor.
DEFAULT_LIMIT = 12
MAX_LIMIT = 50


class FileSearchIndex:
    """Kök başına kısa ömürlü dosya listesi önbelleği."""

    def __init__(self, *, clock: Clock | None = None, ttl_s: float = CACHE_TTL_SECONDS) -> None:
        self._clock = clock or SystemClock()
        self._ttl_s = ttl_s
        self._cache: dict[str, tuple[float, list[str], bool]] = {}

    def paths(self, root: Path) -> tuple[list[str], bool]:
        """Kökteki dosyaların göreli yolları ve tavanın aşılıp aşılmadığı."""
        anahtar = str(root)
        simdi = self._clock.monotonic()
        onbellek = self._cache.get(anahtar)
        if onbellek is not None and simdi - onbellek[0] < self._ttl_s:
            return onbellek[1], onbellek[2]
        mutlak, kisitli = project_files(root)
        goreli = [self._relative(root, yol) for yol in mutlak]
        self._cache[anahtar] = (simdi, goreli, kisitli)
        return goreli, kisitli

    def invalidate(self) -> None:
        """Önbelleği düşür. Kök değiştiğinde çağrılır."""
        self._cache.clear()

    @staticmethod
    def _relative(root: Path, path: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()


def _limit(value: object) -> int:
    """Arayüzden gelen limit; geçersizse varsayılana düşer, tavanı aşamaz."""
    if not isinstance(value, int) or isinstance(value, bool):
        return DEFAULT_LIMIT
    return max(1, min(value, MAX_LIMIT))


def search_project_files(
    index: FileSearchIndex, root: Path, data: dict[str, Any]
) -> dict[str, Any]:
    """Sorguya uyan proje dosyalarını döndür.

    Boş sorgu HATA DEĞİLDİR: `@` yazılır yazılmaz liste açılır ve kullanıcı
    henüz bir şey yazmamıştır.
    """
    sorgu = str(data.get("sorgu", "") or "")
    limit = _limit(data.get("limit"))
    yollar, kisitli = index.paths(root)
    eslesmeler = match_files(yollar, sorgu, limit=limit)
    return {
        "ok": True,
        "sorgu": sorgu,
        "toplam": len(yollar),
        # Tavan aşıldıysa arayüz bunu SÖYLEMELİ: aranan dosya listede yoksa
        # kullanıcı "yok" mu "kesildi" mi bilmeli.
        "kisitli": kisitli,
        "sonuclar": [
            {"yol": item.path, "vurgu": list(item.positions)} for item in eslesmeler
        ],
    }
