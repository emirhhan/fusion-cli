"""Beceri keşif kökleri (P-052) ve yaşam döngüsü: yenile, teşhis, kapatma (P-051).

Ölçüldü (31 Ekim): ~/.agents/skills ve .agents/skills taranmıyordu; --add-dir kökleri beceri
getirmiyordu; katalog oturumda bir kez taranıp bir daha yenilenmiyordu; teşhis yoktu.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from fusion_cli.cli.repl.commands import build_registry
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.tools.capabilities import CapabilityRegistry
from fusion_cli.tools.capability_doctor import diagnose
from fusion_cli.tools.skill_pages import SKILL_TEXT_BUDGET


def _skill(folder: Path, name: str, body: str = "Gövde", description: str = "açıklama") -> None:
    (folder / name).mkdir(parents=True, exist_ok=True)
    (folder / name / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}", encoding="utf-8"
    )


# --- Kökler ---------------------------------------------------------------------- #


def test_agents_skills_kokleri_taranir(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill(home / ".agents" / "skills", "codex-becerisi")
    _skill(root / ".agents" / "skills", "proje-becerisi")

    registry = CapabilityRegistry(home, root)

    assert registry.get_skill("codex-becerisi").source == "codex"  # type: ignore[union-attr]
    assert registry.get_skill("proje-becerisi").source == "proje"  # type: ignore[union-attr]


def test_ek_kokler_beceri_ve_ajan_getirir(tmp_path: Path):
    home, root, ek = tmp_path / "ev", tmp_path / "proje", tmp_path / "diger"
    _skill(ek / ".claude" / "skills", "ek-beceri")
    _skill(ek / ".agents" / "skills", "ek-agents-beceri")
    (ek / ".claude" / "agents").mkdir(parents=True)
    (ek / ".claude" / "agents" / "ek-ajan.md").write_text(
        "---\nname: ek-ajan\ndescription: x\n---\ny", encoding="utf-8"
    )

    yok = CapabilityRegistry(home, root)
    var = yok.with_extra_roots((ek,))

    assert yok.get_skill("ek-beceri") is None
    assert var.get_skill("ek-beceri").source == "ek-kok"  # type: ignore[union-attr]
    assert var.get_skill("ek-agents-beceri") is not None
    assert var.get_agent("ek-ajan") is not None


def test_add_dir_komutu_katalogu_ek_kokle_yeniler(tmp_path: Path):
    home, root, ek = tmp_path / "ev", tmp_path / "proje", tmp_path / "diger"
    root.mkdir()
    _skill(ek / ".claude" / "skills", "ek-beceri")
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    state = ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)
    registry = build_registry(home, skills=lambda: state.capabilities)

    registry.get("add-dir").handler(state, str(ek))  # type: ignore[union-attr]

    assert state.capabilities is not None
    assert state.capabilities.get_skill("ek-beceri") is not None
    assert registry.get("ek-beceri") is not None


# --- Yenileme -------------------------------------------------------------------- #


def test_yeni_eklenen_beceri_kok_degisince_otomatik_gorulur(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill(home / ".claude" / "skills", "ilk")
    registry = CapabilityRegistry(home, root)
    assert [s.name for s in registry.skills()] == ["ilk"]

    _skill(home / ".claude" / "skills", "ikinci")
    # Kök dizinin mtime'ı değişti: imza eşleşmez, katalog yeniden taranır.
    eski = (home / ".claude" / "skills").stat().st_mtime_ns
    os.utime(home / ".claude" / "skills", ns=(eski + 10_000_000, eski + 10_000_000))

    assert {s.name for s in registry.skills()} == {"ilk", "ikinci"}


def test_invalidate_dosya_icerigi_degisikligini_gorur(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill(home / ".claude" / "skills", "x", description="eski")
    registry = CapabilityRegistry(home, root)
    assert registry.get_skill("x").description == "eski"  # type: ignore[union-attr]

    time.sleep(0.01)
    _skill(home / ".claude" / "skills", "x", description="yeni")
    registry.invalidate()

    assert registry.get_skill("x").description == "yeni"  # type: ignore[union-attr]


# --- Teşhis ---------------------------------------------------------------------- #


def test_teshis_eksik_aciklama_kopya_ad_ve_butce_asimini_bulur(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    (home / ".claude" / "skills" / "adsiz").mkdir(parents=True)
    (home / ".claude" / "skills" / "adsiz" / "SKILL.md").write_text("ön madde yok", "utf-8")
    _skill(home / ".claude" / "skills", "kopya", body="A", description="birinci")
    _skill(root / ".claude" / "skills", "kopya", body="B", description="ikinci")
    _skill(home / ".claude" / "skills", "dev", body="x" * (SKILL_TEXT_BUDGET + 10))
    registry = CapabilityRegistry(home, root)

    bulgular = diagnose(registry)

    turler = {(b.kind, b.name) for b in bulgular}
    assert ("eksik_aciklama", "adsiz") in turler
    assert ("frontmatter_yok", "adsiz") in turler
    assert ("kopya_ad", "kopya") in turler
    assert ("uzun_govde", "dev") in turler
    kopya = next(b for b in bulgular if b.kind == "kopya_ad")
    assert "claude" in kopya.detail and "proje" in kopya.detail  # kazanan ve gölgelenen
    assert all(b.severity in ("uyari", "bilgi") for b in bulgular)


def test_teshis_temiz_katalogda_bos(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    _skill(home / ".claude" / "skills", "temiz")

    assert diagnose(CapabilityRegistry(home, root)) == ()


# --- Yapılandırma ---------------------------------------------------------------- #


def test_config_capabilities_disabled_oturum_basinda_kapatir(tmp_path: Path):
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home / ".claude" / "skills", "istenmeyen")
    _skill(home / ".claude" / "skills", "istenen")
    source = tmp_path / "config.yaml"
    source.write_text("capabilities:\n  disabled: [istenmeyen]\n", encoding="utf-8")

    state = ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)

    assert state.config.capabilities.disabled == ("istenmeyen",)
    assert state.capabilities is not None
    assert state.capabilities.get_skill("istenmeyen") is None
    assert state.capabilities.get_skill("istenen") is not None


# --- REPL komutları -------------------------------------------------------------- #


@pytest.fixture
def state(tmp_path: Path) -> ReplState:
    home, root = tmp_path / "ev", tmp_path / "proje"
    root.mkdir()
    _skill(home / ".claude" / "skills", "ilk")
    source = tmp_path / "config.yaml"
    source.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return ReplState(config=load_config(source), memory=null_memory(), root=root, home=home)


def test_skills_reload_ve_doctor(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)
    skills = registry.get("skills")
    assert skills is not None
    _skill(state.home / ".claude" / "skills", "ikinci")

    yenile = skills.handler(state, "reload")
    teshis = skills.handler(state, "doctor")

    assert "2 beceri" in yenile
    assert "ikinci" in skills.handler(state, "")
    assert "sorun bulunmadı" in teshis.lower() or "temiz" in teshis.lower()


def test_skills_new_ve_agents_new_gorev_hazirlar(state: ReplState):
    registry = build_registry(state.home, skills=lambda: state.capabilities)

    beceri = registry.get("skills").handler(state, "new seo-denetimi")  # type: ignore[union-attr]
    gorev_b, _ = state.take_pending()
    ajan = registry.get("agents").handler(state, "new")  # type: ignore[union-attr]
    gorev_a, _ = state.take_pending()

    assert "seo-denetimi" in beceri and ".claude/skills/seo-denetimi/SKILL.md" in gorev_b
    assert "ask_user" in gorev_b and "description" in gorev_b
    assert ".claude/agents/" in gorev_a and "ask_user" in gorev_a
    assert ajan
