"""Araç çağırmadan niyet yazan modele kademeli, somut zorlama."""

from __future__ import annotations

from dataclasses import fields

from fusion_cli.engines.agent import reflexion
from fusion_cli.engines.agent.execution_policy import ExecutionPolicy


def test_ilk_uyari_aracin_kanonik_cagrisini_gosterir():
    metin = reflexion.tool_evidence_required_note("workspace_mutation").content

    assert "eylem-kanıtı-zorunlu" in metin


def test_sonraki_uyarilar_acikalama_yazmadan_tek_arac_cagrisi_ister():
    ikinci = reflexion.tool_evidence_required_note("workspace_mutation", attempt=2).content
    ucuncu = reflexion.tool_evidence_required_note("workspace_mutation", attempt=3).content

    assert "list_dir" in ikinci and "açıklama yazma" in ikinci
    assert "SON" in ucuncu and ucuncu != ikinci


def test_varsayilan_politika_modele_birden_fazla_deneme_hakki_verir():
    varsayilan = next(f for f in fields(ExecutionPolicy) if f.name == "max_evidence_reprompts")

    assert varsayilan.default >= 3
