"""Oyun kapısı: play_probe ile denenen oyun kapanışta yeniden oynatılır (`game_verify`).

Ölçüldü (6 Ekim 2026, dalga23 HTML oyun): play_probe 15 kez "Konsol hatası: 1 —
Assignment to constant variable" ve "oyuncu kıpırdamadı" dedi; araç sonucu yine "ok"
sayıldı, kapı bakmadı, model "tamamlandı" dedi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.core.tools import ToolContext
from fusion_cli.engines.agent import game_verify
from fusion_cli.engines.agent.game_verify import GameProbeVerifier
from fusion_cli.tools.play_probe import ProbeReport

_SAGLAM = ProbeReport((), 60, '{"x":1}', '{"x":2}', True, None, ("ArrowRight",))
_BOZUK = ProbeReport(
    ("Assignment to constant variable.",), 60, '{"x":1}', '{"x":1}', True, None, ()
)


def test_saglam_oyunda_sorun_yok_bozukta_her_sorun_sayilir():
    assert _SAGLAM.problems() == ()
    sorunlar = _BOZUK.problems()
    assert any("Assignment to constant variable" in s for s in sorunlar)
    assert any("tuşlar" in s.lower() for s in sorunlar)
    assert any("döngü" in s for s in ProbeReport((), 3, None, None, None, None).problems())


async def _kapi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rapor: ProbeReport):
    (tmp_path / "index.html").write_text("<canvas></canvas>")
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "game.js")
    context.probed_games.add((tmp_path / "index.html").as_uri())

    async def _sonda(url, keys=()):
        return rapor

    monkeypatch.setattr(game_verify, "probe_game", _sonda)
    return await GameProbeVerifier(context).verify()


async def test_denenen_oyun_kapanista_bozuksa_tur_kapanmaz(tmp_path, monkeypatch):
    sonuc = await _kapi(tmp_path, monkeypatch, _BOZUK)

    assert not sonuc.ok
    assert any("Assignment to constant variable" in f for f in sonuc.findings)


async def test_denenen_oyun_saglamsa_gecer(tmp_path, monkeypatch):
    assert (await _kapi(tmp_path, monkeypatch, _SAGLAM)).ok


async def test_oyun_denenmediyse_kapi_soz_soylemez(tmp_path):
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "game.js")
    assert (await GameProbeVerifier(context).verify()).ok


async def test_oyun_dosyadan_da_acilarak_denenir(tmp_path, monkeypatch):
    """Ölçüldü (dalga24): `type="module"` oyun http'de çalışıyordu, çift tıklayınca
    (file://) CORS yüzünden hiç yüklenmiyordu; Fusion yalnız http'de denemişti."""
    (tmp_path / "index.html").write_text("<canvas></canvas>")
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "game.js")
    context.probed_games.add("http://127.0.0.1:8771/index.html")
    dosya = (tmp_path / "index.html").as_uri()
    denenen: list[str] = []

    async def _sonda(url, keys=()):
        denenen.append(url)
        if url == dosya:
            return ProbeReport(
                ("Access to script blocked by CORS policy",), 60, None, None, None, None
            )
        return _SAGLAM

    monkeypatch.setattr(game_verify, "probe_game", _sonda)

    sonuc = await GameProbeVerifier(context).verify()

    assert dosya in denenen
    assert not sonuc.ok
    assert any("dosyadan" in f and "CORS" in f for f in sonuc.findings)


async def test_denenmemis_canvas_oyunu_da_kapanista_oynatilir(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<canvas id='oyun'></canvas>")
    context = ToolContext(root=tmp_path, task_kinds={"oyun"})
    context.touched.add(tmp_path / "game.js")

    async def _sonda(url, keys=()):
        return _BOZUK

    monkeypatch.setattr(game_verify, "probe_game", _sonda)
    assert not (await GameProbeVerifier(context).verify()).ok


async def test_canvas_olmayan_sayfa_oyun_sayilmaz(tmp_path):
    (tmp_path / "index.html").write_text("<main>blog</main>")
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "index.html")
    assert (await GameProbeVerifier(context).verify()).ok


async def test_oyun_istegi_degilse_denenmemis_canvas_sayfasi_oynatilmaz(tmp_path):
    (tmp_path / "index.html").write_text("<canvas id='grafik'></canvas>")
    context = ToolContext(root=tmp_path)
    context.touched.add(tmp_path / "chart.js")
    assert (await GameProbeVerifier(context).verify()).ok


async def test_oyun_denenemiyorsa_sessiz_basari_sayilmaz(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<canvas></canvas>")
    context = ToolContext(root=tmp_path, task_kinds={"oyun"})
    context.touched.add(tmp_path / "index.html")

    async def unavailable(url, keys=()):
        raise ImportError("Playwright kurulu değil")

    monkeypatch.setattr(game_verify, "probe_game", unavailable)
    result = await GameProbeVerifier(context).verify()
    assert not result.ok
    assert any("doğrulanamadı" in finding for finding in result.findings)
