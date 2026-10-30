"""CLI tablolarında ve satırlarında güvenilmeyen metin Rich işareti sayılmaz (L1-05).

Ölçüldü (30 Ekim): LLM çıktısından öğrenilen ders `[/x]` içerince `fusion memory lessons`
`MarkupError` ile çöküyordu; araç/MCP açıklaması ve hata metni de aynı yoldan basılıyordu.
"""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from fusion_cli.cli import memory_commands, trace_command, trash_commands
from fusion_cli.core.memory import Lesson, LessonKind, ModelStats

KOTU = "ders [/kapanmamis] ve [bold]kalin[/bold] [x"


def _konsol() -> tuple[Console, io.StringIO]:
    tampon = io.StringIO()
    return Console(file=tampon, force_terminal=False, width=160, no_color=True), tampon


def test_ders_tablosu_koseli_parantezli_metinde_cokmez():
    konsol, tampon = _konsol()
    tablo = memory_commands.lessons_table((Lesson(text=KOTU, kind=LessonKind.MISTAKE),))

    konsol.print(tablo)

    assert "[/kapanmamis]" in tampon.getvalue()
    assert "[bold]kalin[/bold]" in tampon.getvalue()


def test_model_istatistik_tablosu_koseli_parantezli_adda_cokmez():
    konsol, tampon = _konsol()
    konsol.print(memory_commands.stats_table((ModelStats("m[/x]", 1, 0.9, 1, 10),)))

    assert "m[/x]" in tampon.getvalue()


def test_iz_ozeti_bulgu_ve_hedefte_cokmez(monkeypatch):
    konsol, tampon = _konsol()
    monkeypatch.setattr(trace_command, "console", konsol)

    class _Ozet:
        pause_reason = "durdu [/x]"
        findings = ("bulgu [/y]",)
        model_calls = tool_calls = blocked_tools = failed_tools = parse_repairs = 0
        steps = verified_steps = 0

        def headline(self) -> str:
            return "ozet [/z]"

    class _Depo:
        def latest(self):
            return "kosu[/q]"

        def runs(self):
            return ["kosu[/q]"]

        def read(self, _kimlik):
            return ()

    monkeypatch.setattr(trace_command, "summarize_run", lambda _olaylar: _Ozet())

    trace_command.render_trace(_Depo(), None)

    cikti = tampon.getvalue()
    assert "bulgu [/y]" in cikti and "durdu [/x]" in cikti and "ozet [/z]" in cikti


def test_cop_tablosu_yolu_isaretsiz_basar(monkeypatch):
    konsol, tampon = _konsol()
    monkeypatch.setattr(trash_commands, "console", konsol)

    class _Girdi:
        id = "k1"
        deleted_at = 0.0
        original = Path("/t/a[/x]b")  # kısa yol: uzun tmp_path tabloda satır kırıp aramayı bozar

    monkeypatch.setattr(trash_commands, "list_trash", lambda _dizin: [_Girdi()])

    trash_commands.show()

    assert "a[/x]b" in tampon.getvalue()


def test_olmayan_kosu_kimligi_temiz_kosu_ozeti_basmaz(monkeypatch):
    """`render_trace` da `trace_text` gibi var olmayan kimliği reddeder (L1-34)."""
    konsol, tampon = _konsol()
    monkeypatch.setattr(trace_command, "console", konsol)

    class _Depo:
        def runs(self):
            return ["gercek"]

        def read(self, _kimlik):
            raise AssertionError("olmayan koşu okunmamalı")

    trace_command.render_trace(_Depo(), "yok-boyle-bir-sey")

    assert "Böyle bir koşu yok" in tampon.getvalue()
    assert "temiz koşu" not in tampon.getvalue()


def test_yetenek_kaldir_yol_kacisini_reddeder(monkeypatch, tmp_path):
    """`kaldir ../x` yetenek kökünün dışına çıkamaz (L1-33)."""
    import pytest
    import typer

    from fusion_cli.cli import capability_commands

    kok = tmp_path / "yetenekler"
    kok.mkdir()
    (tmp_path / "disarida").mkdir()
    monkeypatch.setattr(capability_commands, "capabilities_dir", lambda: kok)
    monkeypatch.setattr(
        capability_commands,
        "move_to_trash",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("çöpe taşınmamalı")),
    )

    with pytest.raises(typer.Exit):
        capability_commands.remove("../disarida")


def test_bozuk_bilgi_paketi_traceback_yerine_temiz_cikis(monkeypatch, tmp_path):
    """Bozuk JSON/eksik alanlı manifest çıplak traceback vermez (L1-32)."""
    import pytest
    import typer

    from fusion_cli.cli import knowledge_commands

    konsol, tampon = _konsol()
    monkeypatch.setattr(knowledge_commands, "console", konsol)
    bozuk = tmp_path / "manifest.json"
    bozuk.write_text("{kapanmamış", encoding="utf-8")

    with pytest.raises(typer.Exit):
        knowledge_commands._read_or_exit(bozuk)

    assert "okunamadı" in tampon.getvalue()
