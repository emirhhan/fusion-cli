"""Görevdeki dosyalar hangi komşu projede duruyor?

Kullanıcı fusion'ı yanlış klasörde açtığında "dosya yok" demek doğrudur ama
yetersizdir: doğru dizin çoğu zaman bir üst klasörün hemen altındadır ve bunu
bulmak tek bir dizin taramasıdır.

DİZİN DEĞİŞTİRİLMEZ, yalnızca ÖNERİLİR. Kök kısıtı (`restrict_to_root`) tam da
kullanıcının açtığı dizinin dışına çıkılmasın diye vardır; "sanırım şunu
kastettin" deyip başka bir projede dosya düzenlemeye başlamak, halüsinasyon gören
bir modelle birleştiğinde kabul edilemez bir risktir. Karar kullanıcınındır.

Tarama SIĞDIR ve yalnızca dizin varlığına bakar: kardeş klasörler + bir alt
katman. Derin arama, büyük ağaçlarda turu bekletirdi.
"""

from __future__ import annotations

from pathlib import Path

#: Taranacak en fazla aday dizin. Sığ tutulur: amaç aramak değil, en olası
#: komşuyu göstermek.
MAX_CANDIDATES = 60
#: Bir adayın önerilebilmesi için eşleşmesi gereken en az yol sayısı.
MIN_MATCHES = 2


def find_workspace_for(paths: tuple[str, ...], root: Path) -> Path | None:
    """Verilen göreli yolların hepsinin bulunduğu komşu dizini ara.

    Birden çok aday eşleşirse `None` döner: belirsiz bir öneri, önerisizlikten
    kötüdür — kullanıcıyı yanlış projeye yönlendirebilir.
    """
    aranan = tuple(dict.fromkeys(p for p in paths if p and not p.startswith("/")))
    if len(aranan) < MIN_MATCHES:
        return None

    bulunan = [aday for aday in _candidates(root) if _matches_all(aday, aranan)]
    return bulunan[0] if len(bulunan) == 1 else None


def _candidates(root: Path) -> list[Path]:
    """Kardeş dizinler VE onların çocukları.

    Çocuk katmanı şart: gerçek yerleşim ölçüldü — kullanıcı `~/Desktop/fusion-cli`
    içinde açtı, aradığı proje `~/Desktop/projeler/GATE HOLDING` idi. Yani hedef,
    kardeşin (`projeler`) çocuğuydu. Yalnızca kardeşlere bakan bir tarama onu
    bulamıyordu.
    """
    adaylar: list[Path] = []
    for kardes in _dirs(root.parent):
        if kardes != root:
            adaylar.append(kardes)
        adaylar.extend(torun for torun in _dirs(kardes) if torun != root)
        if len(adaylar) >= MAX_CANDIDATES:
            break
    return adaylar[:MAX_CANDIDATES]


def _dirs(taban: Path) -> list[Path]:
    try:
        return sorted(p for p in taban.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        # Erişilemeyen dizin bir hata değil: öneri bir iyileştirmedir.
        return []


def _matches_all(aday: Path, aranan: tuple[str, ...]) -> bool:
    return all((aday / yol).exists() for yol in aranan)
