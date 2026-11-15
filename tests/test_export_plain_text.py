"""`/export [filename]` düz metin; argümansız Pano/Dosya seçicisi (#206, Claude Code)."""

from __future__ import annotations

import pytest

from fusion_cli.appserver.commands import command_choices
from fusion_cli.cli.repl.export_commands import export_transcript
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.transcript_export import default_export_name, export_text
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui.clipboard import ClipboardResult

from .fakes import make_config


def _history() -> list[Message]:
    return [
        Message("system", "gizli sistem istemi"),
        Message("user", "Selam"),
        Message(
            "assistant",
            "Okuyorum.",
            tool_calls=(ToolCall(id="1", name="read_file", arguments='{"path": "a.py"}'),),
        ),
        Message("tool", "satır 1\nsatır 2", tool_call_id="1", name="read_file", ok=True),
        Message("assistant", "Cevap: anahtar sk-abcdefghijklmnopqrstuvwxyz0123456789"),
    ]


@pytest.fixture
def state(tmp_path):
    repl = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    repl.history = _history()
    return repl


def test_duz_metin_rolleri_ve_arac_ciktisini_okunur_yazar():
    text = export_text(_history(), title="Selam")

    assert "> Selam" in text
    assert "⏺ Okuyorum." in text
    assert '⏺ read_file({"path": "a.py"})' in text
    assert "  ⎿  satır 1\n     satır 2" in text
    assert "gizli sistem istemi" not in text
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in text
    assert "<details>" not in text and "## " not in text


def test_varsayilan_ad_txt():
    assert default_export_name(ext="txt", now=lambda: 0.0).endswith(".txt")


def test_dosya_adi_uzantisizsa_txt_ve_duz_metin(state, tmp_path):
    sonuc = export_transcript(state, "sohbet", now=lambda: 0.0)

    hedef = tmp_path / "sohbet.txt"
    assert hedef.is_file() and str(hedef) in sonuc
    assert "> Selam" in hedef.read_text(encoding="utf-8")


def test_txt_uzantisi_duz_metin(state, tmp_path):
    export_transcript(state, "notlar.txt")
    assert "⏺ Okuyorum." in (tmp_path / "notlar.txt").read_text(encoding="utf-8")


def test_argumansiz_secici_pano(state):
    yazilan: list[str] = []

    def sahte(text: str) -> ClipboardResult:
        yazilan.append(text)
        return ClipboardResult(True, tool="sahte")

    sonuc = export_transcript(state, "", copier=sahte, picker=lambda choices, **_: "pano")

    assert "panoya" in sonuc
    assert yazilan and "> Selam" in yazilan[0]


def test_argumansiz_secici_dosya(state, tmp_path):
    sonuc = export_transcript(state, "", now=lambda: 0.0, picker=lambda choices, **_: "dosya")

    hedef = tmp_path / default_export_name(ext="txt", now=lambda: 0.0)
    assert hedef.is_file() and str(hedef) in sonuc


def test_argumansiz_secici_vazgec(state, tmp_path):
    sonuc = export_transcript(state, "", picker=lambda choices, **_: None)
    assert sonuc == ""
    assert not list(tmp_path.glob("*.txt"))


def test_masaustu_argumansiz_export_secici_dondurur(state):
    payload = command_choices(state, "export")

    assert payload is not None
    assert [item["deger"] for item in payload["secenekler"]] == ["pano", "dosya"]


@pytest.mark.asyncio
async def test_tui_argumansiz_export_modal_acar_ve_dosyaya_yazar(state, tmp_path):
    import asyncio

    from fusion_cli.cli.repl.tui_loop import _TuiSession

    session = _TuiSession(state)
    task = asyncio.ensure_future(session._command("/export"))
    await asyncio.sleep(0)
    assert session.tui._mode == "choice"  # uygulama-içi modal, nested picker değil
    session.tui._resolve("dosya")
    await task

    assert list(tmp_path.glob("fusion-sohbet-*.txt"))
