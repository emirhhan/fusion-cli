"""Terminal onay arayüzü — sıralama ve etkileşimsiz ortam davranışı."""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.cli.prompter import ConsolePrompter
from fusion_cli.core.tools import Tool, ToolContext
from fusion_cli.engines.agent.approval import build_request


def _prompter(tmp_path, *, flush=None):
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    return ConsolePrompter(console, ToolContext(root=tmp_path), flush=flush), buffer


def _arac(ad="write_file"):
    return Tool(name=ad, description="", parameters={}, run=lambda a, c: None, mutating=True)


async def test_etkilesimsiz_ortamda_onay_reddedilir(tmp_path):
    """Cevap alınamadıysa 'evet' varsaymak kabul edilemez."""
    prompter, _ = _prompter(tmp_path)

    onay = await prompter.confirm(build_request(_arac(), {"path": "a.txt", "content": "x"}))

    assert onay is False


async def test_etkilesimsiz_ortamda_soru_anlasilir_cevap_doner(tmp_path):
    prompter, _ = _prompter(tmp_path)

    cevap = await prompter.ask("hangi renk?")

    assert "etkileşimsiz" in cevap
    assert cevap.strip().lower() not in ("hayır", "evet")


async def test_onay_ekrani_diff_onizlemesi_gosterir(tmp_path):
    (tmp_path / "a.txt").write_text("eski\n", encoding="utf-8")
    prompter, buffer = _prompter(tmp_path)

    await prompter.confirm(build_request(_arac(), {"path": "a.txt", "content": "yeni\n"}))

    cikti = buffer.getvalue()
    assert "-eski" in cikti and "+yeni" in cikti


async def test_yikici_komutta_gerekce_gosterilir(tmp_path):
    prompter, buffer = _prompter(tmp_path)

    await prompter.confirm(build_request(_arac("run_shell"), {"command": "rm -rf build"}))

    assert "geri alınamaz" in buffer.getvalue()


async def test_soru_sirasinda_canli_gosterge_duraklatilir(tmp_path):
    """Agent soru sorarken 'hazırlanıyor…' canlı satırı duraklatılmalı.

    Duraklatılmazsa Live'ın yenileme iş parçacığı her ~100ms'de cevap istemini
    ve kullanıcının yazdığını siler; kullanıcı yazamaz görünür.
    """
    import contextlib

    olaylar: list[str] = []

    @contextlib.contextmanager
    def _suspend():
        olaylar.append("duraklat")
        try:
            yield
        finally:
            olaylar.append("devam")

    async def _flush():
        olaylar.append("bosalt")

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    prompter = ConsolePrompter(console, ToolContext(root=tmp_path), flush=_flush, suspend=_suspend)

    await prompter.ask("soru?")

    # Önce duraklat, en son devam; boşaltma ikisinin arasında kalmalı.
    assert olaylar[0] == "duraklat"
    assert olaylar[-1] == "devam"
    assert "bosalt" in olaylar[1:-1]


async def test_onay_sirasinda_canli_gosterge_duraklatilir(tmp_path):
    import contextlib

    olaylar: list[str] = []

    @contextlib.contextmanager
    def _suspend():
        olaylar.append("duraklat")
        try:
            yield
        finally:
            olaylar.append("devam")

    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=200, no_color=True)
    prompter = ConsolePrompter(console, ToolContext(root=tmp_path), suspend=_suspend)

    await prompter.confirm(build_request(_arac(), {"path": "a.txt", "content": "x"}))

    assert olaylar == ["duraklat", "devam"]


async def test_terminali_devralmadan_once_veriyolu_bosaltilir(tmp_path):
    """Onay paneli, veriyolunda bekleyen çıktının ortasına düşmemeli."""
    sirali = []

    async def _flush():
        sirali.append("bosaltildi")

    prompter, _ = _prompter(tmp_path, flush=_flush)

    await prompter.confirm(build_request(_arac(), {"path": "a.txt", "content": "x"}))
    await prompter.ask("soru?")

    assert sirali == ["bosaltildi", "bosaltildi"]


# --- Resize teşhisi ---------------------------------------------------------- #
#
# prompt_toolkit #1933: terminal yeniden boyutlandırılınca istem kopyalanıyor.
# Kök neden renderer.erase()'in GÖRELİ imleç hareketi; tam genişlikteki
# bottom_toolbar daralmada iki satıra sarıyor ve silme aritmetiği kayıyor.
# Bu anahtar mekanizmayı kod değiştirmeden doğrulamak içindir.


def test_toolbar_varsayilan_olarak_kapalidir(monkeypatch):
    """Tam genişlikteki çubuk resize'da istem kopyası bırakıyordu."""
    from fusion_cli.cli.repl.input import toolbar_enabled

    monkeypatch.delenv("FUSION_TOOLBAR", raising=False)

    assert toolbar_enabled() is False


def test_toolbar_ortam_degiskeniyle_geri_getirilir(monkeypatch):
    from fusion_cli.cli.repl.input import toolbar_enabled

    monkeypatch.setenv("FUSION_TOOLBAR", "1")

    assert toolbar_enabled() is True


# --- İstem satırı ------------------------------------------------------------ #
#
# Alt bilgi çubuğu KALDIRILDI: tam genişlikte bir satır olduğu için terminal
# daraldığında sarıyor ve prompt_toolkit'in resize silme aritmetiğini bozuyordu
# (#1933). Mod bilgisi istemin kendisine taşındı; aynı satırda kaldığı için sarmaz.


def test_istem_modu_gosterir():
    from fusion_cli.cli.repl.input import ReplInput, prompt_fragments
    from fusion_cli.engines.agent.approval import ApprovalMode

    metin = prompt_fragments(ApprovalMode.AUTO)

    assert "auto" in metin
    assert ReplInput is not None


def test_her_mod_kendi_etiketiyle_gosterilir():
    from fusion_cli.cli.repl.input import prompt_fragments
    from fusion_cli.engines.agent.approval import ApprovalMode

    for mod in ApprovalMode:
        assert mod.value in prompt_fragments(mod)


def test_istem_tek_satir_kalir():
    """Sarma olursa resize hatası geri döner; istem kısa olmalı."""
    import re

    from fusion_cli.cli.repl.input import prompt_fragments
    from fusion_cli.engines.agent.approval import ApprovalMode

    for mod in ApprovalMode:
        goruntu = re.sub(r"<[^>]+>", "", prompt_fragments(mod))
        assert len(goruntu) <= 24, f"istem çok uzun: {goruntu!r}"
