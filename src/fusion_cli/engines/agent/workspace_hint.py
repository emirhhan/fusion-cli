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
    """Kardeş dizinler ve onların bir alt katmanı."""
    adaylar: list[Path] = []
    for taban in (root.parent, root.parent.parent):
        for child in _dirs(taban):
            if child == root:
                continue
            adaylar.append(child)
            if len(adaylar) >= MAX_CANDIDATES:
                return adaylar
    return adaylar


def _dirs(taban: Path) -> list[Path]:
    try:
        return sorted(p for p in taban.iterdir() if p.is_dir() and not p.name.startswith("."))
    except OSError:
        # Erişilemeyen dizin bir hata değil: öneri bir iyileştirmedir.
        return []


def _matches_all(aday: Path, aranan: tuple[str, ...]) -> bool:
    return all((aday / yol).exists() for yol in aranan)
