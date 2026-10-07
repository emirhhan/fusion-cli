"""Oyun sondası: tuşlara tepki, rAF, konsol, yeniden başlatma metin olarak raporlanır."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.tools.game_assets import AssetUsage
from fusion_cli.tools.play_probe import DEFAULT_KEYS, ProbeReport, parse_keys, probe_game


def test_henuz_dogmayan_varlik_hata_sayilmaz_ama_kanit_siniri_gosterilir():
    report = ProbeReport(
        (),
        60,
        '{"x":1}',
        '{"x":2}',
        True,
        None,
        ("ArrowRight",),
        asset_usage=AssetUsage(("boss.svg",), ()),
    )
    assert report.problems() == ()
    assert "boss.svg" in report.summary() and "henüz" in report.summary()
    assert "sprite-HUD çakışması" in report.summary()
    assert "HUD okunur" not in report.summary()


_OYUN = """<!doctype html><html><body><canvas id=c width=200 height=100></canvas><script>
const s={durum:'oynuyor',skor:0,can:3,oyuncu:{x:10,y:50}}; const k=new Set();
addEventListener('keydown',e=>{k.add(e.key); if(e.key==='r'){s.oyuncu.x=10;s.skor=0;}});
addEventListener('keyup',e=>k.delete(e.key));
const c=document.getElementById('c').getContext('2d');
(function f(){ if(k.has('ArrowRight')){s.oyuncu.x+=2;s.skor++;}
 c.fillStyle='#000';c.fillRect(0,0,200,100);c.fillStyle='#fff';c.fillRect(s.oyuncu.x,50,10,10);
 requestAnimationFrame(f);})();
window.__GAME_STATE__=()=>s;</script></body></html>"""


def test_tus_listesi_dogrulanir_gecersizde_varsayilan():
    assert parse_keys(["a", "ArrowLeft"]) == ("a", "ArrowLeft")
    assert parse_keys('["Space"]') == ("Space",)
    assert parse_keys("w, s") == ("w", "s")
    assert parse_keys(None) == DEFAULT_KEYS
    assert parse_keys([]) == DEFAULT_KEYS


def test_ozet_degismeyen_durumu_ve_eksik_kancayi_soyler():
    donuk = ProbeReport((), 60, '{"x":1}', '{"x":1}', False, None)
    kancasiz = ProbeReport(("hata",), 5, None, None, None, None)

    assert "TUŞLAR DURUMU DEĞİŞTİRMEDİ" in donuk.summary() and "HAYIR" in donuk.summary()
    assert "__GAME_STATE__ yok" in kancasiz.summary()
    assert "döngü çalışmıyor" in kancasiz.summary()


def test_gercek_oyunda_tuslar_durumu_degistirir_r_sifirlar(tmp_path):
    pytest.importorskip("playwright")
    sayfa = tmp_path / "index.html"
    sayfa.write_text(_OYUN, encoding="utf-8")

    try:
        rapor = asyncio.run(probe_game(sayfa.as_uri(), ("ArrowRight",)))
    except Exception as hata:  # Chromium kurulu değilse ölçüm yapılamaz
        pytest.skip(f"tarayıcı yok: {hata}")

    assert rapor.console_errors == () and rapor.raf_per_second >= 20
    assert rapor.state_before != rapor.state_after and rapor.canvas_changed
    assert rapor.restart_state is not None and '"skor":0' in rapor.restart_state


def test_birbirini_goturen_tuslar_durumu_degistirmedi_sayilmaz():
    """Ölçüldü (4 Ekim): sağ+sol ve sıfırlayan `r` aynı listede gelince önce=sonra çıktı."""
    rapor = ProbeReport((), 60, '{"x":1}', '{"x":1}', True, None, ("ArrowRight", "ArrowLeft"))

    ozet = rapor.summary()

    assert "TUŞLAR DURUMU DEĞİŞTİRMEDİ" not in ozet
    assert "Durumu değiştiren tuşlar: 'ArrowRight', 'ArrowLeft'" in ozet


def test_gercek_oyunda_sifirlayan_tus_listede_olsa_da_etkili_tus_raporlanir(tmp_path):
    pytest.importorskip("playwright")
    sayfa = tmp_path / "index.html"
    sayfa.write_text(_OYUN, encoding="utf-8")

    try:
        rapor = asyncio.run(probe_game(sayfa.as_uri(), ("ArrowRight", "r")))
    except Exception as hata:  # Chromium kurulu değilse ölçüm yapılamaz
        pytest.skip(f"tarayıcı yok: {hata}")

    assert rapor.state_before == rapor.state_after
    assert "ArrowRight" in rapor.effective_keys
    assert "TUŞLAR DURUMU DEĞİŞTİRMEDİ" not in rapor.summary()


_BUTTON_GAME = """<!doctype html><body style='margin:0'>
<canvas id='c' width='1280' height='800'></canvas>
<button id='start'>Başla</button><script>
const s={durum:'menu',skor:0,oyuncu:{x:10,y:50}};
const button=document.getElementById('start');
function start(){s.durum='oynuyor';button.style.display='none';}
START_HANDLER
addEventListener('keydown',e=>{if(e.key==='Enter')start();
 if(s.durum==='oynuyor'&&e.key==='ArrowRight'){s.oyuncu.x+=20;s.skor++;}});
const c=document.getElementById('c').getContext('2d');
(function f(){c.fillStyle='#080808';c.fillRect(0,0,1280,800);
 c.fillStyle='#fff';c.fillRect(s.oyuncu.x,50,20,20);requestAnimationFrame(f);})();
window.__GAME_STATE__=()=>s;</script>"""


async def test_bozuk_basla_dugmesini_klavye_yolu_gizleyemez(tmp_path):
    pytest.importorskip("playwright")
    page = tmp_path / "index.html"
    page.write_text(_BUTTON_GAME.replace("START_HANDLER", ""), encoding="utf-8")
    report = await probe_game(page.as_uri(), ("ArrowRight",))
    assert any("Başla" in problem for problem in report.problems())


async def test_basla_dugmesi_tek_basina_oyunu_baslatiyorsa_gecer(tmp_path):
    pytest.importorskip("playwright")
    page = tmp_path / "index.html"
    page.write_text(
        _BUTTON_GAME.replace("START_HANDLER", "button.addEventListener('click',start);"),
        encoding="utf-8",
    )
    report = await probe_game(page.as_uri(), ("ArrowRight",))
    assert not any("Başla" in problem for problem in report.problems())
    assert report.state_before and '"durum":"oynuyor"' in report.state_before


async def test_menu_animasyonu_basla_dugmesi_calisti_sayilmaz(tmp_path):
    pytest.importorskip("playwright")
    page = tmp_path / "index.html"
    source = _BUTTON_GAME.replace("START_HANDLER", "setInterval(()=>s.oyuncu.x++,30);")
    page.write_text(source, encoding="utf-8")
    report = await probe_game(page.as_uri(), ("ArrowRight",))
    assert any("Başla" in problem for problem in report.problems())


async def test_dugme_gorunur_kalsa_da_baslatma_durum_gecisi_dogrulanir(tmp_path):
    pytest.importorskip("playwright")
    page = tmp_path / "index.html"
    source = _BUTTON_GAME.replace("button.style.display='none';", "").replace(
        "START_HANDLER", "button.addEventListener('click',start);"
    )
    page.write_text(source, encoding="utf-8")
    report = await probe_game(page.as_uri(), ("ArrowRight",))
    assert not any("Başla" in problem for problem in report.problems())
    assert report.state_before and '"durum":"oynuyor"' in report.state_before


async def test_basla_dugmesi_gizlenip_oyun_baslamiyorsa_kalir(tmp_path):
    pytest.importorskip("playwright")
    page = tmp_path / "index.html"
    source = _BUTTON_GAME.replace("s.durum='oynuyor';", "").replace(
        "START_HANDLER", "button.addEventListener('click',start);"
    )
    page.write_text(source, encoding="utf-8")
    report = await probe_game(page.as_uri(), ("ArrowRight",))
    assert any("Başla" in problem for problem in report.problems())
