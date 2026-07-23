"""Zaman bütçeli paralel toplama — straggler ve mutlak üst sınır davranışı."""

from __future__ import annotations

import asyncio

from fusion_cli.core.concurrency import gather_with_cutoff


def _isi(deger, gecikme, basarili=True):
    async def _calis():
        await asyncio.sleep(gecikme)
        return (deger, basarili)

    return _calis


_BASARILI = lambda sonuc: sonuc[1]  # noqa: E731


async def test_bos_liste_bos_doner():
    assert (
        await gather_with_cutoff(
            [], is_success=_BASARILI, enough_success=1, grace_s=1, hard_cap_s=1
        )
        == []
    )


async def test_hepsi_hizliysa_hepsi_toplanir():
    sonuclar = await gather_with_cutoff(
        [_isi("a", 0.0), _isi("b", 0.0), _isi("c", 0.0)],
        is_success=_BASARILI,
        enough_success=2,
        grace_s=0.5,
        hard_cap_s=5.0,
    )

    assert {sonuc[0] for sonuc in sonuclar} == {"a", "b", "c"}


async def test_yeterli_cevap_gelince_yavas_olan_grace_ile_kesilir():
    sonuclar = await gather_with_cutoff(
        [_isi("a", 0.0), _isi("b", 0.0), _isi("cok-yavas", 5.0)],
        is_success=_BASARILI,
        enough_success=2,
        grace_s=0.05,
        hard_cap_s=5.0,
    )

    assert {sonuc[0] for sonuc in sonuclar} == {"a", "b"}


async def test_mutlak_ust_sinir_ilk_basaridan_sonra_isler():
    sonuclar = await gather_with_cutoff(
        [_isi("a", 0.0), _isi("cok-yavas", 5.0)],
        is_success=_BASARILI,
        enough_success=99,  # grace hiç devreye girmez
        grace_s=10.0,
        hard_cap_s=0.05,
    )

    assert [sonuc[0] for sonuc in sonuclar] == ["a"]


async def test_basarisiz_sonuclar_sayilmaz_ama_toplanir():
    sonuclar = await gather_with_cutoff(
        [_isi("hatali", 0.0, basarili=False), _isi("saglam", 0.02)],
        is_success=_BASARILI,
        enough_success=1,
        grace_s=1.0,
        hard_cap_s=5.0,
    )

    assert {sonuc[0] for sonuc in sonuclar} == {"hatali", "saglam"}


async def test_sonuclar_geldikce_geri_cagriya_bildirilir():
    gorulen = []

    await gather_with_cutoff(
        [_isi("a", 0.0), _isi("b", 0.01)],
        is_success=_BASARILI,
        enough_success=2,
        grace_s=1.0,
        hard_cap_s=5.0,
        on_result=lambda sonuc: gorulen.append(sonuc[0]),
    )

    assert gorulen == ["a", "b"]


async def test_kesilen_isler_iptal_edilir_arkada_calismaya_devam_etmez():
    calisti = []

    async def _yavas():
        try:
            await asyncio.sleep(5.0)
        except asyncio.CancelledError:
            calisti.append("iptal")
            raise
        calisti.append("bitti")
        return ("yavas", True)

    await gather_with_cutoff(
        [_isi("a", 0.0), lambda: _yavas()],
        is_success=_BASARILI,
        enough_success=1,
        grace_s=0.05,
        hard_cap_s=5.0,
    )

    assert calisti == ["iptal"]
