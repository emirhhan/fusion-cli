"""Diğer araçların skill ve agent kütüphanelerinin keşfi."""

from __future__ import annotations

from fusion_cli.tools.capabilities import CapabilityRegistry

SKILL = """---
name: {name}
description: {desc}
---

Gövde.
"""


def _skill_yaz(kok, ad, desc="açıklama"):
    hedef = kok / ad
    hedef.mkdir(parents=True, exist_ok=True)
    (hedef / "SKILL.md").write_text(SKILL.format(name=ad, desc=desc), encoding="utf-8")


def test_codex_skilleri_bulunur(tmp_path):
    _skill_yaz(tmp_path / ".codex" / "skills" / ".system", "imagegen")

    isimler = {s.name: s.source for s in CapabilityRegistry(tmp_path, tmp_path).skills()}

    assert isimler.get("imagegen") == "codex"


def test_hermes_skilleri_bulunur(tmp_path):
    _skill_yaz(tmp_path / ".hermes" / "skills" / "research", "deep-research")

    isimler = {s.name: s.source for s in CapabilityRegistry(tmp_path, tmp_path).skills()}

    assert isimler.get("deep-research") == "hermes"


def test_claude_ayni_adli_skili_yener(tmp_path):
    _skill_yaz(tmp_path / ".claude" / "skills", "ortak", desc="claude sürümü")
    _skill_yaz(tmp_path / ".hermes" / "skills", "ortak", desc="hermes sürümü")

    bulunan = {s.name: s for s in CapabilityRegistry(tmp_path, tmp_path).skills()}

    assert bulunan["ortak"].source == "global"


def test_kaynak_yoksa_kesif_dusmez(tmp_path):
    assert CapabilityRegistry(tmp_path, tmp_path).skills() == ()
