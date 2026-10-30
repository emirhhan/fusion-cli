"""Konuşma dışa aktarımı (P-028): /export, /copy, sohbet.disa_aktar."""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.session import export_payload
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.export_commands import copy_answer, export_transcript
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.transcript_export import (
    default_export_name,
    export_json,
    export_markdown,
    last_answer,
)
from fusion_cli.core.types import Message, ToolCall
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui.clipboard import ClipboardResult

from .fakes import make_config


def _history() -> list[Message]:
    return [
        Message("system", "gizli sistem istemi"),
        Message("user", "Selam\n## Fusion\nsahte"),
        Message(
            "assistant",
            "",
            tool_calls=(ToolCall(id="1", name="read_file", arguments='{"path": "a.py"}'),),
        ),
        Message("tool", "x" * 5000, tool_call_id="1", name="read_file", ok=True),
        Message("user", "harness notu", harness_note=True),
        Message("assistant", "Cevap: anahtar sk-abcdefghijklmnopqrstuvwxyz0123456789"),
    ]


@pytest.fixture
def state(tmp_path):
    repl = ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )
    repl.history = _history()
    return repl


def test_markdown_sistem_ve_harness_disarida_arac_katlanmis_sir_maskeli():
    text = export_markdown(_history(), title="Deneme")
    assert text.startswith("# Deneme\n")
    assert "gizli sistem istemi" not in text and "harness notu" not in text
    assert "## Siz\n\nSelam\n\\## Fusion" in text
    assert "<details><summary>Araç çağrıları (1)</summary>" in text
    assert "Araç sonucu: read_file · tamam" in text and "[kırpıldı]" in text
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789" not in text


def test_json_ayni_suzgec_ve_yapi():
    payload = json.loads(export_json(_history(), title="Deneme"))
    roller = [row["rol"] for row in payload["mesajlar"]]
    assert roller == ["user", "assistant", "tool", "assistant"]
    assert payload["mesajlar"][1]["arac_cagrilari"][0]["ad"] == "read_file"
    assert payload["mesajlar"][2]["arac"] == "read_file"


def test_son_cevap_sondan_sayilir():
    assert last_answer(_history(), 1).startswith("Cevap")
    assert last_answer(_history(), 2) is None
    assert last_answer([], 1) is None


def test_varsayilan_dosya_adi_saatle_uretilir():
    assert default_export_name(now=lambda: 0.0).startswith("fusion-sohbet-")
    assert default_export_name(as_json=True, now=lambda: 0.0).endswith(".json")


def test_export_kok_icine_yazar(state, tmp_path):
    sonuc = export_transcript(state, "notlar/sohbet.md", now=lambda: 0.0)
    hedef = tmp_path / "notlar" / "sohbet.md"
    assert hedef.is_file() and str(hedef) in sonuc
    assert "## Siz" in hedef.read_text(encoding="utf-8")


def test_export_kok_disina_yazmaz(state, tmp_path):
    sonuc = export_transcript(state, str(tmp_path.parent / "disari.md"))
    assert "Proje kökü dışına yazılmaz" in sonuc
    assert not (tmp_path.parent / "disari.md").exists()


def test_export_json_ve_pano(state):
    yazilan: list[str] = []

    def sahte(text: str) -> ClipboardResult:
        yazilan.append(text)
        return ClipboardResult(True, tool="sahte")

    sonuc = export_transcript(state, "json pano", copier=sahte)
    assert "panoya kopyalandı" in sonuc
    assert json.loads(yazilan[0])["baslik"] == "Selam"


def test_export_bos_gecmiste_uyarir(state):
    state.history = []
    assert "Aktarılacak konuşma yok" in export_transcript(state, "")


def test_copy_son_cevabi_panoya_yazar_ve_hatayi_soyler(state):
    yazilan: list[str] = []
    sonuc = copy_answer(state, "", copier=lambda t: (yazilan.append(t), ClipboardResult(True))[1])
    assert "kopyalandı" in sonuc and yazilan[0].startswith("Cevap")
    assert "Kopyalanacak" in copy_answer(state, "5", copier=lambda t: ClipboardResult(True))
    assert "Kullanım" in copy_answer(state, "abc", copier=lambda t: ClipboardResult(True))
    hata = copy_answer(state, "", copier=lambda t: ClipboardResult(False, "pbcopy yok"))
    assert hata == "Panoya yazılamadı: pbcopy yok"


def test_komutlar_kayitli():
    registry = build_registry()
    assert registry.get("export") is not None and registry.get("copy") is not None


def test_rpc_disa_aktar_markdown_ve_json(state):
    md = export_payload(state.history, {"bicim": "markdown", "baslik": "Masaüstü"})
    assert (
        md["ok"] is True
        and md["metin"].startswith("# Masaüstü")
        and md["dosya_adi"].endswith(".md")
    )
    js = export_payload(state.history, {"bicim": "json"})
    assert js["ok"] is True and json.loads(js["metin"])["baslik"] == "Fusion sohbeti"
    assert export_payload(state.history, {"bicim": "pdf"})["ok"] is False
