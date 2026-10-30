"""REPL önekleri (P-022): `!` kabuk, `@dosya` anma, `#` bellek notu ve tamamlama."""

from __future__ import annotations

import io

import pytest
from prompt_toolkit.document import Document
from rich.console import Console

from fusion_cli.cli.repl import prefixes
from fusion_cli.cli.repl.completion import ReplCompleter, fuzzy_match, path_suggestions
from fusion_cli.cli.repl.loop import apply_mentions, run_shell_prefix_line
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.core.memory import LessonSource
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


class _Dersler:
    def __init__(self):
        self.eklenen = []

    def add(self, lesson):
        self.eklenen.append(lesson)
        return True


@pytest.fixture
def state(tmp_path):
    return ReplState(
        config=make_config(), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


# --- Saf ayrıştırma ---------------------------------------------------------- #


def test_kabuk_oneki_ayrisir():
    assert prefixes.shell_command("! ls -la") == "ls -la"
    assert prefixes.shell_command("!git status") == "git status"
    assert prefixes.shell_command("!") is None
    assert prefixes.shell_command("!!") is None
    assert prefixes.shell_command("!= operatörü nedir") is None
    assert prefixes.shell_command("merhaba") is None


def test_not_oneki_ayrisir():
    assert prefixes.memory_note("# testleri her zaman çalıştır") == "testleri her zaman çalıştır"
    assert prefixes.memory_note("#1234 nedir") is None
    assert prefixes.memory_note("## başlık") is None
    assert prefixes.memory_note("#!/bin/sh") is None
    assert prefixes.memory_note("#   ") is None


def test_dosya_anmalari_bulunur_eposta_ve_tekrar_elenir():
    found = prefixes.mentions(
        "@src/a.py ile @src/a.py karşılaştır, ali@ornek.com'a yazma. @README.md."
    )
    assert [m.raw for m in found] == ["src/a.py", "README.md"]
    assert not any(m.is_resource for m in found)


def test_mcp_kaynak_bicimi_taninir():
    (found,) = prefixes.mentions("@github:issues/42 oku")
    assert found.is_resource and found.server == "github" and found.resource == "issues/42"
    (dosya,) = prefixes.mentions("@C:/proje/x.py")
    assert not dosya.is_resource


# --- Yan etkiler -------------------------------------------------------------- #


def test_anilan_dosya_baglama_eklenir_mesaj_degismez(state, tmp_path):
    (tmp_path / "notlar.txt").write_text("içerik 123", encoding="utf-8")
    (tmp_path / "alt").mkdir()
    notes = apply_mentions("@notlar.txt ve @alt dizinine bak", state)
    assert len(state.pending_context) == 2
    assert "içerik 123" in state.pending_context[0]
    assert "andığı dizin" in state.pending_context[1]
    assert notes[0].startswith("@notlar.txt bağlama eklendi")
    # Bir sonraki tur bağlamı BİR KEZ alır.
    assert "içerik 123" in state.take_pending_digest()
    assert state.pending_context == [] and state.take_pending_digest() == ""


def test_olmayan_dosya_ve_mcp_kaynagi_notla_gecilir(state):
    result = prefixes.expand_mentions("@yok.py @sunucu:kaynak", state)
    assert result.blocks == ()
    assert "okunamadı" in result.notes[0]
    assert "MCP kaynak anması henüz desteklenmiyor" in result.notes[1]


def test_buyuk_dosya_kirpilir(state, tmp_path):
    (tmp_path / "buyuk.txt").write_text("x" * (prefixes.MENTION_MAX_CHARS + 50), encoding="utf-8")
    result = prefixes.expand_mentions("@buyuk.txt", state)
    assert f"ilk {prefixes.MENTION_MAX_CHARS} karakter" in result.blocks[0]
    assert len(result.blocks[0]) < prefixes.MENTION_MAX_CHARS + 200


@pytest.mark.asyncio
async def test_kabuk_komutu_calisir_ve_ciktisi_baglama_girer(state):
    result = await prefixes.run_shell_prefix(state, "echo merhaba-fusion")
    assert result.ok and "merhaba-fusion" in result.output
    assert state.pending_context and "$ echo merhaba-fusion" in state.pending_context[0]
    assert "yeniden çalıştırma" in state.take_pending_digest()


@pytest.mark.asyncio
async def test_plan_kipinde_kabuk_calismaz(state):
    state.approval = ApprovalMode.PLAN
    result = await prefixes.run_shell_prefix(state, "echo olmasin")
    assert not result.ok and result.output == "" and state.pending_context == []
    assert "Plan kipinde" in result.notes[0]


@pytest.mark.asyncio
async def test_kabuk_satiri_konsola_basilir(state):
    console = Console(file=io.StringIO(), force_terminal=False, no_color=True, width=120)
    await run_shell_prefix_line("echo selam", state, console)
    out = console.file.getvalue()
    assert "$ echo selam" in out and "selam" in out and "bağlamına eklendi" in out


def test_not_derse_kaydedilir(state):
    dersler = _Dersler()
    state.memory = type("B", (), {"lessons": dersler, "enabled": True})()
    assert "kaydedildi" in prefixes.add_memory_note(state, "yalnız pytest kullan")
    assert dersler.eklenen[0].text == "yalnız pytest kullan"
    assert dersler.eklenen[0].source is LessonSource.MANUAL


# --- Tamamlama ---------------------------------------------------------------- #


def test_fuzzy_eslesme_sirali_alt_dizi():
    assert fuzzy_match("transcript_store.py", "tsp")
    assert not fuzzy_match("abc", "ca")


def test_yol_onerileri_dizin_icinde_gezer_ve_gurultuyu_atlar(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "model.py").write_text("", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".gizli").write_text("", encoding="utf-8")
    assert path_suggestions("", (tmp_path,)) == ["src/"]
    assert path_suggestions("src/m", (tmp_path,)) == ["src/main.py", "src/model.py"]
    assert path_suggestions("src/mdl", (tmp_path,)) == ["src/model.py"]
    assert path_suggestions(".", (tmp_path,)) == [".gizli"]


def test_tamamlayici_komut_ve_yol_ayirir(tmp_path):
    (tmp_path / "okubeni.md").write_text("", encoding="utf-8")
    completer = ReplCompleter(["/help", "/health"], (tmp_path,))
    komutlar = [c.text for c in completer.get_completions(Document("/he"), None)]
    assert komutlar == ["/health", "/help"] or set(komutlar) == {"/help", "/health"}
    yollar = [c.text for c in completer.get_completions(Document("şunu incele @oku"), None)]
    assert yollar == ["@okubeni.md"]
    # Satır ortasındaki `/` komut değildir (yol olabilir).
    assert list(completer.get_completions(Document("bak /he"), None)) == []
