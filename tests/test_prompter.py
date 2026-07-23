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


async def test_terminali_devralmadan_once_veriyolu_bosaltilir(tmp_path):
    """Onay paneli, veriyolunda bekleyen çıktının ortasına düşmemeli."""
    sirali = []

    async def _flush():
        sirali.append("bosaltildi")

    prompter, _ = _prompter(tmp_path, flush=_flush)

    await prompter.confirm(build_request(_arac(), {"path": "a.txt", "content": "x"}))
    await prompter.ask("soru?")

    assert sirali == ["bosaltildi", "bosaltildi"]
