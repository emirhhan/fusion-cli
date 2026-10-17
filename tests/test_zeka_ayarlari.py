"""Zeka ayarları: durum, kalıcı yazım, canlı uygulama, doğrulama."""

from __future__ import annotations

import pytest

from fusion_cli.appserver import intelligence
from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.execution_mode import ExecutionMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def make_state(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)
    state = ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path)
    return state, hedef


def flag(durum, anahtar):
    return next(item for item in durum["bayraklar"] if item["anahtar"] == anahtar)


def test_durum_motor_plan_kipi_ve_her_anahtari_anlatir(tmp_path):
    state, _ = make_state(tmp_path)
    durum = intelligence.status(state)
    assert durum["ok"] and durum["motor"] == "agent" and durum["planKipi"] == "off"
    assert {e["deger"] for e in durum["motorlar"]} == {"agent", "fusion"}
    assert {e["deger"] for e in durum["planKipleri"]} == {"off", "always"}
    anahtarlar = {item["anahtar"] for item in durum["bayraklar"]}
    assert {
        "self_review",
        "lessons",
        "playbooks",
        "visual_verification",
        "teacherless",
    } <= anahtarlar
    for item in durum["bayraklar"]:
        assert item["etiket"] and item["aciklama"] and item["maliyet"] and item["grup"]


def test_ogretmene_danis_ters_calisir_acik_demek_teacherless_false(tmp_path):
    state, hedef = make_state(tmp_path)
    assert flag(intelligence.status(state), "teacherless")["acik"] is True  # varsayılan: danışır
    sonuc = intelligence.apply(state, {"anahtar": "teacherless", "deger": False})
    assert sonuc["ok"] and flag(sonuc, "teacherless")["acik"] is False
    assert state.config.runtime.teacherless is True
    assert load_config(hedef).runtime.teacherless is True


@pytest.mark.parametrize("anahtar", ["visual_verification", "playbooks", "lessons", "self_review"])
def test_anahtar_kalici_yazilir_ve_canli_uygulanir(tmp_path, anahtar):
    state, hedef = make_state(tmp_path)
    simdiki = bool(getattr(state.config.runtime, anahtar))
    sonuc = intelligence.apply(state, {"anahtar": anahtar, "deger": not simdiki})
    assert sonuc["ok"] and flag(sonuc, anahtar)["acik"] is (not simdiki)
    assert bool(getattr(state.config.runtime, anahtar)) is (not simdiki)
    assert bool(getattr(load_config(hedef).runtime, anahtar)) is (not simdiki)


def test_diger_runtime_ayarlari_yazimda_korunur(tmp_path):
    state, hedef = make_state(tmp_path)
    hedef.write_text("runtime:\n  agent_max_idle_rounds: 7\n", encoding="utf-8")
    intelligence.apply(state, {"anahtar": "playbooks", "deger": True})
    assert load_config(hedef).runtime.agent_max_idle_rounds == 7


def test_plan_kipi_kalici_ve_canli(tmp_path):
    state, hedef = make_state(tmp_path)
    sonuc = intelligence.apply(state, {"anahtar": "planKipi", "deger": "always"})
    assert sonuc["ok"] and sonuc["planKipi"] == "always"
    assert state.config.runtime.workflow_mode is ExecutionMode.ALWAYS
    assert load_config(hedef).runtime.workflow_mode is ExecutionMode.ALWAYS
    assert intelligence.apply(state, {"anahtar": "planKipi", "deger": "auto"})["ok"] is False


def test_motor_secimi_oturumda_uygulanir_gecersiz_reddedilir(tmp_path):
    state, _ = make_state(tmp_path)
    assert intelligence.apply(state, {"anahtar": "motor", "deger": "fusion"})["motor"] == "fusion"
    assert state.engine is Engine.FUSION
    reddedilen = intelligence.apply(state, {"anahtar": "motor", "deger": "uydurma"})
    assert reddedilen["ok"] is False and state.engine is Engine.FUSION


def test_bilinmeyen_anahtar_ve_bool_olmayan_deger_reddedilir(tmp_path):
    state, hedef = make_state(tmp_path)
    assert intelligence.apply(state, {"anahtar": "agent_max_steps", "deger": True})["ok"] is False
    assert intelligence.apply(state, {"anahtar": "lessons", "deger": "evet"})["ok"] is False
    assert intelligence.apply(state, "bozuk")["ok"] is False
    assert not hedef.exists()  # reddedilen istek dosyaya hiçbir şey yazmaz
