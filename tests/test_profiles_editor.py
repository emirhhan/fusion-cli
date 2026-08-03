"""`/profiles` editörü — profil listeleme ve baş model düzenleme (uygunluk filtreli)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.cli.repl import profiles_flow
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.models import ProfileEligibility
from fusion_cli.config.profile import resolve_tier_name  # noqa: F401 (varlık kontrolü)
from fusion_cli.core.types import ModelSpec
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages


@pytest.fixture
def config(tmp_path):
    from fusion_cli.config.loader import load_config

    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return load_config(hedef)


@pytest.fixture
def state(config, tmp_path):
    return ReplState(config=config, memory=null_memory(), root=tmp_path)


def _pick(value):
    def _p(choices, *, title, gradient_rows=False, stream=None):
        _p.gorulen = choices
        return value

    _p.gorulen = ()
    return _p


def _run(state, satir):
    name, argument = parse(satir)
    return build_registry().get(name).handler(state, argument)


# --- listeleme ------------------------------------------------------------- #


def test_profiles_kademeleri_bas_modeliyle_listeler(state):
    mesaj = _run(state, "/profiles")
    assert "low" in mesaj and "medium" in mesaj and "high" in mesaj
    assert "→" in mesaj  # her satır baş modeli gösterir


def test_profiles_edit_kullanim_hatasi(state):
    assert _run(state, "/profiles edit") == messages.PROFILES_EDIT_USAGE


def test_bilinmeyen_profil_hata(state):
    mesaj = _run(state, "/profiles edit efsanevi")
    assert "efsanevi" in mesaj


# --- baş modeli düzenleme -------------------------------------------------- #


def test_bas_model_secilince_uygulanir(config):
    tier = config.tier_by_name("high")
    hedef = tier.candidates[-1]  # farklı bir aday
    result = profiles_flow.edit_profile_primary(config, "high", picker=_pick(hedef.name))
    # Seçilen aday kademenin agent'ı olur ve uygulanır.
    guncel = result.config.tier_by_name("high")
    assert guncel.agent.name == hedef.name
    assert result.config.agent.name == hedef.name


def test_duzenlemekten_vazgecmek(config):
    result = profiles_flow.edit_profile_primary(config, "medium", picker=_pick(None))
    assert result.message == messages.PICKER_CANCELLED
    assert result.config is config


# --- uygunluk filtresi + uyumsuzları göster (Faz 2b tamamlanışı) ----------- #


def _config_with_notools(config):
    """medium kademesine araçsız (no-tools) bir aday ekle."""
    medium = config.tier_by_name("medium")
    aracsiz = ModelSpec(name="aracsiz-web", model="web/opak", tags=("no-tools",))
    yeni = replace(medium, candidates=(*medium.candidates, aracsiz))
    tiers = tuple(yeni if t.name == "medium" else t for t in config.tiers)
    # medium eşiği araçsıza izin vermez (allow_no_tools=False).
    elig = dict(config.profile_eligibility)
    elig["medium"] = ProfileEligibility(min_context=0, allow_no_tools=False)
    return replace(config, tiers=tiers, profile_eligibility=elig)


def test_uyumsuz_aday_varsayilan_gizlenir(config):
    cfg = _config_with_notools(config)
    picker = _pick(None)
    profiles_flow.edit_profile_primary(cfg, "medium", picker=picker)
    adlar = [c.value for c in picker.gorulen]
    assert "aracsiz-web" not in adlar  # araçsız aday gizli


def test_uyumsuz_aday_incompatible_ile_gerekceyle_gorunur(config):
    cfg = _config_with_notools(config)
    picker = _pick(None)
    profiles_flow.edit_profile_primary(cfg, "medium", picker=picker, show_incompatible=True)
    satirlar = {c.value: c.description for c in picker.gorulen}
    assert "aracsiz-web" in satirlar
    assert "UYUMSUZ" in satirlar["aracsiz-web"]
    assert "araç desteği yok" in satirlar["aracsiz-web"]


def test_komuttan_incompatible_bayragi_gecer(state, monkeypatch):
    cfg = _config_with_notools(state.config)
    state.config = cfg
    yakalanan = {}

    def _fake_edit(config, tier_name, *, picker=None, show_incompatible=False):
        yakalanan["incompatible"] = show_incompatible
        from fusion_cli.cli.repl.model_flows import FlowResult

        return FlowResult(config, "ok")

    monkeypatch.setattr(profiles_flow, "edit_profile_primary", _fake_edit)
    _run(state, "/profiles edit medium incompatible")
    assert yakalanan["incompatible"] is True
