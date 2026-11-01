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
