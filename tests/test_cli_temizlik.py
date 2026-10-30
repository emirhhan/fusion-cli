"""CLI koşu sonu temizliği ve paperclip onay semantiği (L1-06, L1-07, L1-27)."""

from __future__ import annotations

import asyncio

import pytest

from fusion_cli.cli import cleanup, paperclip_command
from fusion_cli.engines.agent.approval import ApprovalAnswer


def test_mcp_kapanisi_patlasa_da_tarayici_kapatilir(monkeypatch):
    """Ölçüldü (30 Ekim): iki ardışık await try/finally'siz; ilki fırlatınca tarayıcı sızıyordu."""
    cagrilar: list[str] = []

    async def _mcp():
        cagrilar.append("mcp")
        raise RuntimeError("mcp kapanmadı")

    async def _tarayici():
        cagrilar.append("tarayici")

    monkeypatch.setattr("fusion_cli.mcp_bridge.pool.close_mcp_pool", _mcp)
    monkeypatch.setattr("fusion_cli.providers.web_browser.close_all_browser_sessions", _tarayici)

    async def _is():
        return 7

    assert asyncio.run(cleanup.with_web_cleanup(_is())) == 7
    assert cagrilar == ["mcp", "tarayici"]


def test_is_istisnasi_temizlik_hatasiyla_maskelenmez(monkeypatch):
    async def _mcp():
        raise RuntimeError("temizlik hatası")

    async def _tarayici():
        return None

    monkeypatch.setattr("fusion_cli.mcp_bridge.pool.close_mcp_pool", _mcp)
    monkeypatch.setattr("fusion_cli.providers.web_browser.close_all_browser_sessions", _tarayici)

    async def _is():
        raise ValueError("asıl hata")

    with pytest.raises(ValueError, match="asıl hata"):
        asyncio.run(cleanup.with_web_cleanup(_is()))


def test_paperclip_komutu_web_temizligiyle_calisir(monkeypatch):
    """`paperclip` koşusu da tarayıcı/MCP temizliğinden geçer (L1-06)."""
    gorulen: list[str] = []

    async def _koşu(*args, **kwargs):
        class _Sonuc:
            final_text = "bitti"
            ok = True

        return _Sonuc()

    async def _temizlik(coro):
        gorulen.append("temizlik")
        return await coro

    monkeypatch.setattr(paperclip_command, "run_agent_task", _koşu)
    monkeypatch.setattr(paperclip_command, "with_web_cleanup", _temizlik)
    monkeypatch.setattr(paperclip_command, "load_config", lambda: object())
    monkeypatch.setattr(
        paperclip_command,
        "environ_snapshot",
        lambda: {"PAPERCLIP_API_URL": "http://x", "PAPERCLIP_API_KEY": "k"},
    )

    paperclip_command.paperclip()

    assert gorulen == ["temizlik"]


def test_etkilesimsiz_heartbeat_onayi_ulasilamadi_doner():
    """Kimseye sorulamadı ≠ kullanıcı reddetti (L1-07)."""
    onaylayici = paperclip_command._no_prompter(None)

    cevap = asyncio.run(onaylayici.confirm(object()))

    assert cevap is ApprovalAnswer.UNAVAILABLE


# --- Diff: içeriği '--'/'++' ile başlayan satır başlık sayılmaz (L1-21) ---------- #


def _sql_diff() -> str:
    from fusion_cli.tools.diffing import unified_diff

    return unified_diff("a\n-- eski yorum\nb\n", "a\nb\n++ yeni\n", "x.sql")


def test_render_diff_cift_tireli_silinen_satiri_sayar():
    from fusion_cli.ui.diff import render_diff

    sonuc = render_diff(_sql_diff())

    assert sonuc.removed == 1
    assert sonuc.added == 1
    assert "eski yorum" in sonuc.body.plain


def test_onay_onizlemesinde_silinen_tireli_satir_kirmizi_boyanir():
    from fusion_cli.cli.prompter import _colorize_diff
    from fusion_cli.ui import theme

    govde = _colorize_diff(_sql_diff())
    satirlar = govde.plain.splitlines()
    # Gerçek başlıklar soluk; hunk içindeki '--- eski yorum' kırmızı olmalı.
    indeks = next(i for i, satir in enumerate(satirlar) if "eski yorum" in satir)
    konum = sum(len(satir) + 1 for satir in satirlar[:indeks])
    stil = next(s.style for s in govde.spans if s.start <= konum < s.end)
    assert stil == theme.ERROR


def test_gercek_dosya_basliklari_hala_atlanir():
    from fusion_cli.ui.diff import render_diff

    sonuc = render_diff(_sql_diff())

    assert "a/x.sql" not in sonuc.body.plain and "b/x.sql" not in sonuc.body.plain
