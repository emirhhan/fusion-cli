"""`@` ile dosya anmada sorguyu yollara eşleştiren saf puanlayıcı.

Ağ, dosya sistemi ve saat yoktur; girdi bir yol listesi ve bir sorgudur.
Bu sayede sıralama kararı doğrudan test edilir — hangi dosyanın neden önce
geldiği tartışılabilir bir davranıştır, gizli bir sezgi değil.

Tasarım kararı: eşleşme ALT DİZİ (subsequence) üzerinden çalışır, çünkü
kullanıcı yolu baştan sona yazmaz — `wbr` ile `providers/web_browser.py`
bulunabilmeli. Ama alt dizi tek başına gürültülü: neredeyse her uzun yol her
kısa sorguyu içerir. Bu yüzden puan üç şeyi ödüllendirir ve sıralama bunların
toplamı değil, ÖNCELİK SIRASIDIR:

1. Dosya ADINDA eşleşme, yolun geri kalanındaki eşleşmeden önce gelir —
   kullanıcı `Composer` yazarken `screens/Composer.tsx` ister, `composer` geçen
   bir CSS dosyasını değil.
2. Bitişik (alt-dizge) eşleşme, dağınık alt diziden önce gelir.
3. Eşleşme ne kadar erken başlıyorsa o kadar iyidir.

Eşitlikte kısa yol önce gelir ve son çare alfabetiktir; böylece aynı sorgu her
zaman aynı listeyi verir (kararsız sıralama kullanıcıyı şaşırtır).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FileMatch", "match_files"]


@dataclass(frozen=True, slots=True)
class FileMatch:
    """Eşleşen bir yol ve eşleşmenin hangi karakterlerde olduğu.

    `positions` arayüzün eşleşen harfleri vurgulaması içindir; boş sorguda
    boştur.
    """

    path: str
    positions: tuple[int, ...]


def _subsequence(hedef: str, sorgu: str, *, offset: int = 0) -> tuple[int, ...] | None:
    """`sorgu`nun `hedef` içindeki İLK alt dizi konumları; yoksa None."""
    konumlar: list[int] = []
    aranan = iter(enumerate(hedef))
    for harf in sorgu:
        for indeks, mevcut in aranan:
            if mevcut == harf:
                konumlar.append(indeks + offset)
                break
        else:
            return None
    return tuple(konumlar)


def _score(path: str, sorgu: str) -> tuple[tuple[int, int, int, str], tuple[int, ...]] | None:
    """Sıralama anahtarı ve vurgu konumları; eşleşme yoksa None.

    Anahtar küçükten büyüğe sıralanır (0 = en iyi). Kademeler açıkça ayrıdır:
    bir kademedeki HER sonuç, bir alttakinin HEPSİNDEN önce gelir. Toplam puan
    yerine kademe kullanılıyor çünkü toplamda kısa bir yol, doğru dosyayı
    geçebiliyordu — ölçüldü: `composer` sorgusu `docs/composer-notlari.md`'yi
    `screens/Composer.tsx`'in önüne koyuyordu.
    """
    kucuk_yol = path.casefold()
    egik = kucuk_yol.rfind("/")
    ad = kucuk_yol[egik + 1 :]
    ad_offset = egik + 1
    nokta = ad.rfind(".")
    govde = ad if nokta <= 0 else ad[:nokta]

    def _ad_konumlari(yer: int) -> tuple[int, ...]:
        return tuple(range(ad_offset + yer, ad_offset + yer + len(sorgu)))

    # 0) Uzantısız dosya adı sorgunun AYNISI — kullanıcı tam bunu yazdı.
    if govde == sorgu:
        return (0, 0, len(path), path), _ad_konumlari(0)

    yer = ad.find(sorgu)
    # 1) Dosya adı sorguyla BAŞLIYOR.
    if yer == 0:
        return (1, 0, len(path), path), _ad_konumlari(0)
    # 2) Dosya adının içinde bitişik geçiyor.
    if yer > 0:
        return (2, yer, len(path), path), _ad_konumlari(yer)

    # 3) Dosya adında dağınık alt dizi (`cmpsr` → `Composer`).
    konumlar = _subsequence(ad, sorgu, offset=ad_offset)
    if konumlar is not None:
        return (3, konumlar[0] - ad_offset, len(path), path), konumlar

    # 4) Yolun geri kalanında bitişik geçiyor (`screens/` gibi klasör adı).
    yer = kucuk_yol.find(sorgu)
    if yer >= 0:
        return (4, yer, len(path), path), tuple(range(yer, yer + len(sorgu)))

    # 5) Tüm yolda dağınık alt dizi — en zayıf ama yine de eşleşme.
    konumlar = _subsequence(kucuk_yol, sorgu)
    if konumlar is not None:
        return (5, konumlar[0], len(path), path), konumlar

    return None


def match_files(paths: list[str], query: str, *, limit: int = 12) -> list[FileMatch]:
    """Sorguya uyan yolları en iyiden kötüye sırala.

    Boş sorgu ELEMEZ: `@` yazılır yazılmaz liste açılmalı, kullanıcı ne
    yazacağını bilmeden önce de proje dosyalarını görebilmeli.
    """
    sorgu = query.strip().casefold()
    if not sorgu:
        return [FileMatch(path=yol, positions=()) for yol in sorted(paths)[:limit]]

    puanlar: list[tuple[tuple[int, int, int, str], str, tuple[int, ...]]] = []
    for yol in paths:
        sonuc = _score(yol, sorgu)
        if sonuc is None:
            continue
        anahtar, konumlar = sonuc
        puanlar.append((anahtar, yol, konumlar))

    # Anahtarın son alanı yolun kendisi: eşitlikte sıra alfabetik ve KARARLIDIR.
    puanlar.sort(key=lambda item: item[0])
    return [FileMatch(path=yol, positions=konumlar) for _, yol, konumlar in puanlar[:limit]]
