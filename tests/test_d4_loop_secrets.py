"""Takılma sorusu harici öğretmene giderken hata satırını maskeler (A2-14)."""

from __future__ import annotations

from fusion_cli.engines.agent import loop


def test_takilma_sorusundaki_hata_imzasi_maskelenir(monkeypatch):
    sir = "sk-" + "a1b2c3d4e5f6g7h8i9j0k1l2"
    monkeypatch.setattr(loop, "_top_failure", lambda state: ("run_shell", f"401 anahtar {sir}", 3))

    soru = loop._plateau_question(None, "sebep", object())  # type: ignore[arg-type]

    assert sir not in soru and "run_shell" in soru


def test_sikistirma_esigi_cagriyi_yapacak_modelden_hesaplanir():
    from fusion_cli.core.types import ModelSpec

    from .fakes import make_config

    devir = ModelSpec(name="ogretmen", model="devir/model")
    deps = loop.AgentDeps.__new__(loop.AgentDeps)
    deps.config = make_config()
    deps.task_type = "coding"
    deps.task_requirements = ()
    deps.execution = None
    deps.active_model_override = devir

    assert loop._context_spec(deps) is devir
