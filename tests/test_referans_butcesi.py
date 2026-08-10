"""Fusion'ın kendi referans bloğu da bütçelidir ve BÖLÜM SINIRINDA kesilir.

Ölçüldü: kullanıcının kütüphanesinden gelen skill metni 2.500 karakterle
bütçeleniyordu (`INJECT_BUDGET`), ama fusion'ın kendi `web_reference.md` dosyası
20.877 karakterle kırpılmadan enjekte ediliyordu — 8,3 kat asimetri.

Neden önemli: mesaj kutusunun tavanı 32.316 karakter (deneyle ölçüldü) ve
promptun tamamı ~44.000 karakter. Yani referans bloğu tek başına promptu tavanın
üstüne çıkarıyor ve kuyruk — kullanıcının GÖREVİ — düşüyordu.

Kesme düz karakter sayısıyla yapılamaz: dosya ölçek tabloları ve kod örnekleri
içeriyor, tablonun ortasından kesmek modele yarım satır bırakır. Bütün bölümler
korunur, sığmayan bölüm hiç girmez.
"""

from __future__ import annotations

from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.skill_recall import REFERENCE_BUDGET, reference_block


def test_referans_butceyi_asmaz() -> None:
    blok = reference_block(TaskKind.WEBSITE)

    assert 0 < len(blok) <= REFERENCE_BUDGET


def test_bolum_ortasindan_kesilmez() -> None:
    """Kesilen yer her zaman bir `## ` başlığının hemen öncesidir."""
    blok = reference_block(TaskKind.WEBSITE)
    tam = reference_block(TaskKind.WEBSITE, budget=10**9)

    assert len(tam) > len(blok), "test anlamlı olsun diye tam metin daha uzun olmalı"
    # Kırpılmış blok, tam metnin bir ÖNEKİDİR ve bölüm sınırında biter.
    assert tam.startswith(blok.rstrip())
    kalan = tam[len(blok.rstrip()) :].lstrip()
    assert kalan.startswith("## "), f"bölüm ortasından kesilmiş: {kalan[:80]!r}"


def test_ilk_bolumler_korunur() -> None:
    """Sığan bölümler dosya sırasıyla alınır; temel ölçekler başta yazılıdır."""
    blok = reference_block(TaskKind.WEBSITE)

    assert "## Ölçekler" in blok


def test_referanssiz_turde_bos_doner() -> None:
    assert reference_block(TaskKind.TEST) == ""
