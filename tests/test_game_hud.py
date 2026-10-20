"""Ekrandaki can/skor yazısı oyun durumuyla uyuşmalı; oyun sonunda yeniden başlat çalışmalı.

Ölçüldü (dalga47): R'ye basınca durum can=3'e döndü, ekran "Can: 0" kaldı; sonda R'ye
yalnız oyun ortasında bastığı için kusur kapıdan geçti.
"""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.tools.game_hud import PLAYING_LABELS, hud_mismatches, hud_numbers


def test_hud_yazisindan_sayilar_okunur():
    assert hud_numbers(["Skor: 120", "Can: 2", "BÖLÜM 1"]) == {"skor": 120, "can": 2}
    assert hud_numbers(["Lives 3", "Score=40"]) == {"can": 3, "skor": 40}


def test_ekrandaki_can_durumdan_farkliysa_kusur():
    sorunlar = hud_mismatches(["Can: 0"], '{"durum":"playing","can":3}')

    assert len(sorunlar) == 1
    assert "'can: 0'" in sorunlar[0] and "can=3" in sorunlar[0]


def test_uyusan_hud_ya_da_durum_kancasi_yoksa_kusur_yok():
    assert hud_mismatches(["Can: 3", "Skor: 5"], '{"can":3,"skor":5}') == ()
    assert hud_mismatches(["Can: 0"], None) == ()
    assert hud_mismatches(["Can: 0"], '{"durum":"menu"}') == ()


def test_oyun_surerken_skor_sayarak_artabilir_kusur_sayilmaz():
    assert hud_mismatches(["Skor: 90"], '{"skor":100,"can":3}', PLAYING_LABELS) == ()


_OYUN = """<!doctype html><html><body><div id="hud"><span id="can">Can: 3</span>
<span id="skor">Skor: 0</span></div><button id="yeniden" style="display:none">YENİDEN</button>
<script>
let durum='playing', can=3, skor=0;
window.__GAME_STATE__=()=>({durum, can, skor});
const ciz=()=>{document.getElementById('can').textContent='Can: '+can;
  document.getElementById('skor').textContent='Skor: '+skor;};
const bitir=()=>{can=0;skor=50;ciz();durum='gameover';
  document.getElementById('yeniden').style.display='block';};
const basla=()=>{durum='playing';can=3;skor=0;if(DUZGUN)ciz();
  document.getElementById('yeniden').style.display='none';};
addEventListener('keydown',(e)=>{if(e.key==='r'&&durum==='gameover')basla();});
setTimeout(bitir,400);
</script></body></html>"""


async def _sonda(url: str) -> tuple[str, ...]:
    from playwright.async_api import async_playwright

    from fusion_cli.tools.game_hud import restart_after_end

    durum = """() => JSON.stringify(window.__GAME_STATE__())"""
    async with async_playwright() as p:
        tarayici = await p.chromium.launch()
        sayfa = await tarayici.new_page()
        await sayfa.goto(url)
        sonuc = await restart_after_end(sayfa, durum)
        await tarayici.close()
    return sonuc


@pytest.mark.parametrize(("duzgun", "beklenen"), [(False, 2), (True, 0)])
def test_oyun_sonunda_yeniden_baslatinca_hud_sifirlanmali(tmp_path, duzgun, beklenen):
    playwright = pytest.importorskip("playwright.async_api")
    sayfa = tmp_path / "index.html"
    sayfa.write_text(_OYUN.replace("DUZGUN", "true" if duzgun else "false"), encoding="utf-8")
    try:
        sorunlar = asyncio.run(_sonda(sayfa.as_uri()))
    except playwright.Error as hata:
        pytest.skip(f"tarayıcı yok: {hata}")

    assert len(sorunlar) == beklenen
    assert all(sorun.startswith("yeniden başlattıktan sonra") for sorun in sorunlar)
