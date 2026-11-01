"""`/code-review` (takma ad `/review`, #214)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.cli.repl import code_review
from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.macros import Mode
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory


@pytest.fixture
def state(tmp_path: Path, monkeypatch) -> ReplState:
    monkeypatch.setenv("FUSION_MEMORY_DIR", str(tmp_path / "bellek"))
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(
        config=load_config(source), memory=null_memory(), root=tmp_path, home=tmp_path / "ev"
    )


def test_ayristirma_seviye_bayrak_hedef():
    request = code_review.parse("high --fix --comment --max-findings 5 main...ozellik")
    assert not isinstance(request, str)
    assert (request.level, request.fix, request.comment) == ("high", True, True)
    assert request.max_findings == "5" and request.target == "main...ozellik"
    request = code_review.parse("/fix-issue 123")
    assert not isinstance(request, str) and request.level is None
    assert request.target == "/fix-issue 123"
    assert code_review.parse("--max-findings sifir").startswith("Kullanım")
    assert code_review.parse("--bilinmez").startswith("Kullanım")


def test_review_takma_ad_fork_alt_ajanda_ve_seviyeyi_hatirlar(state: ReplState):
    registry = build_registry()
    review = registry.get("review")
    assert review is not None and review.name == "code-review"
    out = review.handler(state, "low 1234")
    assert state.pending_mode is Mode.SUBTASK
    assert "1234" in state.pending_task and "en emin" in state.pending_task
    assert "Yalnız rapor" in state.pending_task
    out = review.handler(state, "--fix --max-findings all")
    assert "low seviyesi yeniden" in out
    assert "çalışma ağacına uygula" in state.pending_task and "sınır yok" in state.pending_task
    review.handler(state, "max")
    assert "temizlik" in state.pending_task and "sınır yok" in state.pending_task
    review.handler(state, "--max-findings default")
    assert "sınır yok" not in state.pending_task and "max seviyesi" in review.handler(state, "")


def test_ultra_bulut_yok_mesaji(state: ReplState):
    out = build_registry().get("code-review").handler(state, "ultra --fix")
    assert "bulut" in out and not state.pending_task


def test_masaustu_bulgu_listesi_ister_terminal_istemez(state: ReplState):
    """Claude Code ReportFindings (#214): bulgu listesi isteyen uygulamada her seviyede."""
    from fusion_cli.cli.repl import code_review_findings as findings

    registry = build_registry()
    registry.get("code-review").handler(state, "low")
    assert not findings.is_findings_turn(state.pending_task)
    state.findings_host = True
    registry.get("code-review").handler(state, "high main")
    assert findings.is_findings_turn(state.pending_task)
    assert "```findings" in state.pending_task and "failure_scenario" in state.pending_task


def test_bulgu_blogu_ayiklanir_dogrulanir_metinden_cikar():
    from fusion_cli.appserver.session import findings_payload
    from fusion_cli.cli.repl import code_review_findings as findings

    text = (
        "İki hata buldum.\n\n```findings\n"
        '[{"file": "src/a.py", "line": "12", "summary": "None kontrolü yok", '
        '"failure_scenario": "boş girdi → AttributeError", "verdict": "confirmed", '
        '"category": "correctness", "short_summary": "None kontrolü"},'
        ' {"file": "b.py", "summary": "satırsız"}, "çöp"]\n```\n'
    )
    payload = findings_payload(text)
    assert payload["metin"] == "İki hata buldum."
    assert payload["bulgular"] == [
        {
            "file": "src/a.py",
            "line": 12,
            "summary": "None kontrolü yok",
            "failure_scenario": "boş girdi → AttributeError",
            "short_summary": "None kontrolü",
            "category": "correctness",
            "verdict": "CONFIRMED",
        }
    ]
    assert findings_payload("blok yok") == {}
    assert findings.extract("```findings\nbozuk json\n```") is None
    empty = findings.extract("```findings\n[]\n```")
    assert empty is not None and empty.findings == () and empty.text == findings.NO_FINDINGS
    many = (
        "```findings\n"
        + str([{"file": "a", "line": 1, "summary": "s", "failure_scenario": "f"}] * 40).replace(
            "'", '"'
        )
        + "\n```"
    )
    assert len(findings.extract(many).findings) == findings.MAX_FINDINGS
