"""Kurulu bir geçmiş kaynağında sınırlı metin araması.

Arama neden burada, uygulamada değil? Çünkü seçicinin elindeki liste kaynağın
TAMAMI değildir: sayfa sayfa çekilir. İstemci tarafında filtrelemek, yalnızca o
ana kadar indirilmiş sayfalarda arama yapmak demektir; eski bir sohbet hiçbir
zaman kapsama girmez. Üstelik Claude deposundaki oturumların çoğunda `ai-title`
kaydı yoktur ve başlık tarih/boyut yedeğine düşer — başlığa bakan bir arama
pratikte hiçbir şey bulamaz. Bu yüzden eşleşme İÇERİKTE aranır.

Sınırlar `tools/search.py` ile aynı sözleşmeyi taşır: tarama kooperatiftir,
kesilen sonuç sessizce "bulunamadı" olmaz, `partial` ile açıkça bildirilir.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..core.redaction import redact
from .models import HistorySource, SessionRef, Turn

#: Tek aramada dönecek en fazla oturum. Seçici listesi bundan uzun olamaz.
MAX_RESULTS = 30

#: İçeriği açılacak en fazla oturum. Depo binlerce dosya tutabilir; arama
#: kullanıcı yazarken çalıştığı için tarama tavanı olmadan yazma gecikir.
MAX_SCANNED_SESSIONS = 200

#: Bir oturumdan okunacak en fazla tur. Uzun sohbetlerin tamamı taranmaz;
#: aranan kelime konuşmanın başında geçme eğilimindedir.
MAX_SCANNED_TURNS = 200

#: Tek `read` çağrısında istenecek tur sayısı.
SCAN_PAGE_SIZE = 50

#: Tüm aramanın kooperatif süre bütçesi (saniye).
SEARCH_DEADLINE_S = 3.0

#: Eşleşme çevresinden gösterilecek en fazla karakter.
SNIPPET_CHARS = 160

_SCAN_LIMIT_REASON = "Tarama sınırına ulaşıldı; daha eski oturumlara bakılmadı."
_RESULT_LIMIT_REASON = "Sonuç sınırına ulaşıldı; daha fazla eşleşme olabilir."
_DEADLINE_REASON = "Arama süre bütçesi doldu; tarama yarıda kesildi."

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionMatch:
    """Sorguyla eşleşen tek bir oturum ve eşleşmenin kanıtı."""

    ref: SessionRef
    #: Eşleşmenin geçtiği yerin maskelenmiş, kısaltılmış parçası.
    snippet: str
    #: Eşleşme başlıkta mı bulundu? Değilse içerikte bulunmuştur.
    in_title: bool


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Aramanın sonucu ve NE KADARININ tarandığı.

    `partial` sonucun eksik olabileceğini söyler. Bunu ayrı taşımak zorunludur:
    aksi halde sınıra takılmış bir tarama, gerçekten sonuç olmayan bir aramadan
    ayırt edilemez ve kullanıcıya yanlışlıkla "yok" denir.
    """

    matches: tuple[SessionMatch, ...]
    #: Künyesine bakılan oturum sayısı.
    scanned: int
    partial: bool
    #: Kesilme nedeni; kesilme yoksa boş.
    reason: str = ""


def search_sessions(
    source: HistorySource,
    query: str,
    root: Path | None = None,
    *,
    limit: int = MAX_RESULTS,
    scan_limit: int = MAX_SCANNED_SESSIONS,
    turn_limit: int = MAX_SCANNED_TURNS,
    deadline_s: float = SEARCH_DEADLINE_S,
    monotonic: Callable[[], float] = time.monotonic,
) -> SearchResult:
    """`query` metnini `source` oturumlarının başlık ve içeriğinde ara.

    Önce başlığa bakılır — künye zaten elde olduğu için bu bedavadır ve dosya
    açtırmaz. Başlık tutmazsa oturum içeriği sayfa sayfa okunur.
    """
    _dogrula(limit, scan_limit, turn_limit)
    needle = _fold(query.strip())
    if not needle:
        return SearchResult(matches=(), scanned=0, partial=False)

    baslangic = monotonic()
    refs = _adaylar(source, root, scan_limit)
    matches: list[SessionMatch] = []
    scanned = 0
    reason = ""

    for ref in refs:
        if monotonic() - baslangic >= deadline_s:
            reason = _DEADLINE_REASON
            break
        scanned += 1
        eslesme = _eslestir(source, ref, needle, turn_limit)
        if eslesme is not None:
            matches.append(eslesme)
            if len(matches) >= limit:
                reason = _RESULT_LIMIT_REASON
                break

    if not reason and len(refs) >= scan_limit:
        reason = _SCAN_LIMIT_REASON
    return SearchResult(
        matches=tuple(matches), scanned=scanned, partial=bool(reason), reason=reason
    )


def _dogrula(limit: int, scan_limit: int, turn_limit: int) -> None:
    """Sınırlar pozitif olmalı; 0 veya negatif sessizce 'sonuç yok' üretemez."""
    for ad, deger in (("limit", limit), ("scan_limit", scan_limit), ("turn_limit", turn_limit)):
        if deger < 1:
            raise ValueError(f"{ad} en az 1 olmalı, {deger} verildi")


def _adaylar(source: HistorySource, root: Path | None, scan_limit: int) -> tuple[SessionRef, ...]:
    """Taranacak künyeler. Kaynak sınırında geniş yakalama bilinçlidir: tek bir
    bozuk depo tüm aramayı düşürmemelidir."""
    try:
        return source.list(root, limit=scan_limit)
    except OSError:
        _logger.warning("geçmiş kaynağı aranamadı: %s", source.name)
        return ()


def _eslestir(
    source: HistorySource, ref: SessionRef, needle: str, turn_limit: int
) -> SessionMatch | None:
    """Önce başlık, sonra içerik. İlk eşleşmede durur."""
    if needle in _fold(ref.title):
        return SessionMatch(ref=ref, snippet=_snippet(ref.title, needle), in_title=True)
    for turn in _turlar(source, ref.session_id, turn_limit):
        if needle in _fold(turn.text):
            return SessionMatch(ref=ref, snippet=_snippet(turn.text, needle), in_title=False)
    return None


def _turlar(source: HistorySource, session_id: str, turn_limit: int) -> tuple[Turn, ...]:
    """Oturumu sayfa sayfa oku; `turn_limit` turda dur."""
    toplanan: list[Turn] = []
    cursor = 0
    while len(toplanan) < turn_limit:
        try:
            sayfa = source.read(session_id, cursor=cursor, limit=SCAN_PAGE_SIZE)
        except OSError:
            _logger.warning("geçmiş oturumu okunamadı: %s/%s", source.name, session_id)
            break
        if not sayfa:
            break
        toplanan.extend(sayfa)
        cursor += len(sayfa)
        if len(sayfa) < SCAN_PAGE_SIZE:
            break
    return tuple(toplanan[:turn_limit])


def _snippet(text: str, needle: str) -> str:
    """Eşleşmenin çevresinden maskelenmiş, sınırlı bir parça üret.

    Maskeleme kesmeden ÖNCE uygulanır: önce kesip sonra maskelemek, yarısı
    kırpılmış bir anahtarı desene uymadığı için maskesiz bırakırdı.
    """
    guvenli = redact(text)
    konum = _fold(guvenli).find(needle)
    if konum < 0:
        return guvenli[:SNIPPET_CHARS].strip()
    yarim = max((SNIPPET_CHARS - len(needle)) // 2, 0)
    bas = max(konum - yarim, 0)
    parca = guvenli[bas : bas + SNIPPET_CHARS].strip()
    return f"…{parca}" if bas > 0 else parca


def _fold(text: str) -> str:
    """Türkçe farkını koruyarak küçült.

    `str.lower()` tek başına yanlıştır: `I` harfini `i` yapar, oysa Türkçede
    `I`'nın küçüğü `ı`'dır. Arayüz `toLocaleLowerCase("tr")` kullandığı için
    sunucu tarafının da aynı eşleşmeyi üretmesi gerekir.
    """
    return text.replace("I", "ı").replace("İ", "i").lower()
