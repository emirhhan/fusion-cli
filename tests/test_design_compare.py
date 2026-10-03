"""Yapılan sayfayı kaynak ölçümle karşılaştırma (`design_compare`).

Ölçüldü (2 Ekim 2026, 8. kabul koşusu): görsel okuyamayan model, boş kahraman alanını,
madde imli menüyü ve yazıyla çizilmiş logoyu fark etmedi; araç "sayfa hatasız açıldı" dedi.
"""

from __future__ import annotations

from fusion_cli.tools import design_compare


def _bolum(tur: str, yukseklik: int, **ek) -> dict:
    return {"kind": tur, "height": yukseklik, "images": [], "headings": [], **ek}


KAYNAK = {
    "url": "https://m.test/",
    "logo": "https://m.test/logo.svg",
    "fonts": {"used": [{"value": "Inter"}, {"value": "Oswald"}]},
    "layout": {"header": {"height": 60}},
    "navigation": {
        "layout": "yatay",
        "menu": [{"text": "ERKEK", "href": "https://m.test/erkek"}, {"text": "KADIN", "href": "x"}],
    },
    "sections": [
        _bolum("kahraman", 720, video={"src": "v.mp4", "poster": ""}),
        _bolum("urun-listesi", 900, images=["a.jpg"]),
        _bolum("gorsel-izgara", 800, images=["b.jpg", "c.jpg"]),
        _bolum("alt-bilgi", 700),
    ],
    "products": [{"name": f"Ürün {n}"} for n in range(24)],
}


def test_ayni_olcum_fark_uretmez():
    assert design_compare.compare(KAYNAK, KAYNAK) == []


def test_olaydaki_sayfanin_farklari_adiyla_soylenir():
    yapilan = {
        "url": "http://127.0.0.1:8770/",
        "logo": '<svg><text x="0">SNEAKS UP</text></svg>',
        "fonts": {"used": [{"value": "Inter"}]},
        "layout": {"header": {"height": 60}},
        "navigation": {
            "layout": "dikey",
            "bullets": True,
            "header": [{"text": "Erkek", "href": "/erkek"}],
        },
        "invisible": [{"text": "MEET ME IN THE CITY", "color": "rgb(255, 255, 255)"}],
        # Üst bilgi ayrı bölüm sayılmış: sıra numarasıyla eşleştirme her şeyi kaydırırdı.
        "sections": [
            _bolum("ust-bilgi", 60),
            _bolum("kahraman", 720),
            _bolum("gorsel-izgara", 1600, images=["b.jpg"]),
        ],
        "products": [],
    }

    farklar = design_compare.compare(KAYNAK, yapilan)
    metin = "\n".join(farklar)

    assert farklar[0].startswith("GÖRÜNMEYEN YAZI") and "MEET ME IN THE CITY" in farklar[0]
    assert "LOGO: logo yazıyla çizilmiş" in metin
    assert "madde imi" in metin and "alt alta" in metin
    assert "şu öğeler üst bilgide yok: KADIN" in metin
    assert "YAZI TİPİ" in metin and "Oswald" in metin
    assert "EKSİK BÖLÜM: kaynakta 2. sırada ürün şeridi/ızgarası" in metin
    # Hizalama türe göredir: kahraman kahramanla eşleşir ve boş olduğu söylenir.
    assert "BÖLÜM 1 (kahraman (tam genişlik açılış)): kaynakta video var" in metin
    assert "BÖLÜM 3 (görsel ızgarası): yükseklik kaynakta 800px, sayfanda 1600px" in metin
    assert "ÜRÜNLER: kaynak sayfada 24+ ürün kartı" in metin
    assert len(farklar) <= design_compare.MAX_DIFFERENCES


def test_kaynak_sayfa_yapilan_sayfanin_turune_gore_secilir():
    ana = {"url": "https://m.test/"}
    liste = {"url": "https://m.test/erkek", "products": [{"name": "x"}] * 20}
    urun = {"url": "https://m.test/u/1", "product": {"name": "Hoodie"}}
    sayfalar = [ana, liste, urun]

    sec = design_compare.pick_reference
    assert sec(sayfalar, {"url": "http://127.0.0.1:8770/"}) is ana
    # Ana sayfada kartların "sepete ekle" düğmesi ürün sayfası sanılmamalı.
    assert sec(sayfalar, {"url": "http://127.0.0.1:8770/", "product": {"name": "y"}}) is ana
    assert sec(sayfalar, {"url": "http://127.0.0.1:8770/urun/a/", "product": {"name": "y"}}) is urun
    kategori = {"url": "http://127.0.0.1:8770/shop/", "products": [{"name": "x"}] * 8}
    assert sec(sayfalar, kategori) is liste
    assert sec(sayfalar, {"url": "http://127.0.0.1:8770/hakkimizda/"}) is None
    assert sec([], {"url": "http://127.0.0.1:8770/"}) is None


def test_urun_sayfasinda_dugme_ve_secenek_farklari_soylenir():
    kaynak = {
        "product": {
            "images": ["1.jpg", "2.jpg", "3.jpg"],
            "options": ["S", "M", "S", "M"],
            "buyButton": {"background": "rgb(22, 38, 255)", "color": "rgb(255, 255, 255)"},
        }
    }
    yapilan = {
        "product": {
            "images": ["1.jpg"],
            "options": [],
            "buyButton": {"background": "rgb(0, 0, 0)", "color": "rgb(255, 255, 255)"},
        }
    }

    metin = "\n".join(design_compare.compare(kaynak, yapilan))

    assert "kaynakta 3 büyük galeri görseli var, sayfanda 1" in metin
    assert "zemin kaynakta rgb(22, 38, 255), sayfanda rgb(0, 0, 0)" in metin
    assert "yazı rengi" not in metin
    assert "seçenekler (S, M) var, sayfanda yok" in metin


def test_kartta_yinelenen_ad_soylenir():
    yapilan = {
        "products": [
            {"name": "Air 1", "text": "Air 1 Air 1 $8,999 Sepete Ekle Sepete Ekle"},
        ]
    }

    metin = "\n".join(design_compare.compare({"products": []}, yapilan))

    assert "ÜRÜN KARTI: ad kartta iki kez yazılıyor ('Air 1')" in metin
    assert (
        design_compare.compare({"products": []}, {"products": [{"name": "A", "text": "A 1 TL"}]})
        == []
    )
