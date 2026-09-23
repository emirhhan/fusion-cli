"""`@` ile dosya anmada sıralama davranışı.

Hangi dosyanın neden önce geldiği tartışılabilir bir karardır; bu testler o
kararı kilitler. Saf modül — ağ ve dosya sistemi yok.
"""

from __future__ import annotations

from fusion_cli.core.file_match import match_files

YOLLAR = [
    "app/src/screens/Composer.tsx",
    "app/src/screens/Composer.css",
    "app/src/screens/Composer.test.tsx",
    "docs/composer-notlari.md",
    "src/fusion_cli/providers/web_browser.py",
    "src/fusion_cli/core/repo_map.py",
    "README.md",
]


def _yollar(sorgu: str, limit: int = 12) -> list[str]:
    return [item.path for item in match_files(YOLLAR, sorgu, limit=limit)]


def test_tam_dosya_adi_esleşmesi_en_one_gelir():
    """Ölçülen hata: kısa yol kayırması doğru dosyayı geçiyordu.

    `composer` sorgusu `docs/composer-notlari.md`'yi (kısa yol)
    `screens/Composer.tsx`'in önüne koyuyordu. Kademe sıralaması bunu düzeltti:
    uzantısız adı sorgunun AYNISI olanlar her zaman önce gelir.
    """
    sonuc = _yollar("composer")

    assert sonuc[:2] == ["app/src/screens/Composer.css", "app/src/screens/Composer.tsx"]
    assert sonuc.index("docs/composer-notlari.md") > 1


def test_uzantiyla_yazilan_tam_ad_tek_dosyayi_bulur():
    assert _yollar("Composer.tsx")[0] == "app/src/screens/Composer.tsx"


def test_dagitik_alt_dizi_uzun_adi_bulur():
    """Kullanıcı yolu baştan sona yazmaz: `wbr` → `web_browser.py`."""
    assert _yollar("wbr")[0] == "src/fusion_cli/providers/web_browser.py"


def test_klasor_adiyla_da_bulunur():
    """Eşleşme dosya adında yoksa yolun geri kalanına bakılır."""
    sonuc = _yollar("providers")

    assert sonuc[0] == "src/fusion_cli/providers/web_browser.py"


def test_buyuk_kucuk_harf_ayrimi_yok():
    assert _yollar("COMPOSER.TSX")[0] == "app/src/screens/Composer.tsx"


def test_bos_sorgu_listeyi_elemez():
    """`@` yazılır yazılmaz liste açılmalı; kullanıcı henüz ne aradığını yazmadı."""
    sonuc = match_files(YOLLAR, "", limit=3)

    assert len(sonuc) == 3
    assert all(item.positions == () for item in sonuc)


def test_eslesmeyen_sorgu_bos_doner():
    assert _yollar("zzzqqq") == []


def test_limit_asilmaz():
    assert len(_yollar("o", limit=2)) == 2


def test_siralama_kararlidir():
    """Aynı sorgu her çağrıda aynı listeyi vermeli."""
    assert _yollar("s") == _yollar("s")


def test_vurgu_konumlari_gercekten_eslesen_harfleri_gosterir():
    """Arayüz bu konumları kalınlaştırıyor; yanlışsa yanlış harf vurgulanır."""
    (eslesme,) = match_files(["src/core/repo_map.py"], "repo", limit=1)

    yol = "src/core/repo_map.py"
    assert "".join(yol[i] for i in eslesme.positions).casefold() == "repo"
