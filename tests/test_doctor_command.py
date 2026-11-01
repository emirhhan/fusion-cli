"""`/doctor prompt-audit [path]` ve `/checkup` takma adı (#212, Claude Code commands)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry, renders_itself
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    root = tmp_path / "proje"
    root.mkdir()
    return ReplState(config=load_config(source), memory=null_memory(), root=root, home=tmp_path)


def _handler(name: str = "doctor"):
    command = build_registry().get(name)
    assert command is not None
    return command.handler


def test_checkup_doctor_takma_adidir() -> None:
    registry = build_registry()
    assert registry.get("checkup") is registry.get("doctor")


def test_prompt_audit_talimat_denetimini_dondurur(state: ReplState) -> None:
    (state.root / "AGENTS.md").write_text("# Kurallar\nTestleri koş.\n", "utf-8")

    rapor = _handler()(state, "prompt-audit")

    assert "AGENTS.md" in rapor
    assert messages.REPL_DOCTOR_PROMPT_DEPRECATED not in rapor
    assert not renders_itself("doctor", "prompt-audit")


def test_prompt_audit_yol_verilince_o_dizini_denetler(state: ReplState, tmp_path: Path) -> None:
    baska = tmp_path / "baska"
    baska.mkdir()
    (baska / "CLAUDE.md").write_text("# Başka proje\n", "utf-8")

    rapor = _handler()(state, f"prompt-audit {baska}")

    assert "CLAUDE.md" in rapor


def test_prompt_audit_dosya_yolu_ust_dizini_denetler(state: ReplState, tmp_path: Path) -> None:
    baska = tmp_path / "baska"
    baska.mkdir()
    (baska / "CLAUDE.md").write_text("# Başka proje\n", "utf-8")

    assert "CLAUDE.md" in _handler()(state, f"prompt-audit {baska / 'CLAUDE.md'}")


def test_prompt_audit_olmayan_yol_hata_verir(state: ReplState, tmp_path: Path) -> None:
    rapor = _handler()(state, f"prompt-audit {tmp_path / 'yok'}")
    assert rapor == messages.REPL_DOCTOR_PATH_MISSING.format(path=tmp_path / "yok")


def test_eski_prompt_adi_bir_kez_uyarir(state: ReplState) -> None:
    ilk = _handler()(state, "prompt")
    ikinci = _handler()(state, "prompt")

    assert ilk.startswith(messages.REPL_DOCTOR_PROMPT_DEPRECATED)
    assert messages.REPL_DOCTOR_PROMPT_DEPRECATED not in ikinci


def _report(*checks):
    from fusion_cli.cli.doctor import DoctorReport
    from fusion_cli.config.readiness import Readiness, ReadinessReport

    return DoctorReport(tuple(checks), ReadinessReport(Readiness.READY, True, True, True))


def test_sorunsuz_teshis_duzeltme_turu_hazirlamaz() -> None:
    from fusion_cli.cli.doctor import Check
    from fusion_cli.cli.repl.doctor_command import fix_task

    assert fix_task(_report(Check("PATH", "tamam", ok=True), Check("bilgi", "x"))) == ""


def test_sorunlu_teshis_onayli_duzeltme_gorevi_uretir() -> None:
    """Claude Code `/doctor` (#212): teşhis + onayla düzeltme; onaysız değişiklik yok."""
    from fusion_cli.cli.doctor import Check
    from fusion_cli.cli.repl.doctor_command import fix_task

    task = fix_task(_report(Check("PATH", "fusion yok", ok=False, remedy="PATH'e ekle")))
    assert "PATH: fusion yok (öneri: PATH'e ekle)" in task
    assert "ask_user" in task and "onay vermediği" in task


async def test_doctor_render_sorun_varsa_bekleyen_tur_kurar(
    state: ReplState, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rich.console import Console

    from fusion_cli.cli import doctor
    from fusion_cli.cli.repl import help_view

    monkeypatch.setattr(
        doctor,
        "diagnose",
        lambda live=False: _report(doctor.Check("Anahtar", "yok", ok=False, remedy="ekle")),
    )
    console = Console(record=True, width=120)
    await help_view.render("doctor", state, build_registry(), console)
    assert "düzeltme önerileri" in console.export_text()
    task, _ = state.take_pending()
    assert "Anahtar: yok" in task
