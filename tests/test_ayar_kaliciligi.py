"""Ayarlar KALICI olmalı: değiştir → yeniden aç → değer duruyor.

Ölçülen sorun: zeka motoru ve izin modu yalnız `ReplState`'te yaşıyordu;
uygulama kapanıp açılınca (ya da çıkış sonrası pencere yenilenince) tek ajana /
`auto` kipine dönüyordu.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fusion_cli.appserver import intelligence, ui_prefs
from fusion_cli.cli.repl.state import Engine, ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.config.writer import (
    write_approval_mode,
    write_engine,
    write_runtime_flag,
    write_theme,
    write_workflow_mode,
)
from fusion_cli.engines.agent.approval import ApprovalMode
from fusion_cli.memory.factory import null_memory

from .fakes import make_config


def _state(tmp_path: Path) -> tuple[ReplState, Path]:
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)
    return ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path), hedef


def test_motor_yazilip_yeniden_acilinca_durur(tmp_path):
    hedef = tmp_path / "config.yaml"
    write_engine(make_config(source=hedef), "fusion", hedef)
    assert load_config(hedef).runtime.engine == "fusion"


def test_gecersiz_motor_ve_izin_modu_reddedilir(tmp_path):
    hedef = tmp_path / "c.yaml"
    config = make_config(source=hedef)
    with pytest.raises(ValueError, match="motor"):
        write_engine(config, "bilinmeyen", hedef)
    with pytest.raises(ValueError, match="izin"):
        write_approval_mode(config, "bilinmeyen", hedef)


def test_izin_modu_yazilip_yeniden_acilinca_durur(tmp_path):
    hedef = tmp_path / "config.yaml"
    write_approval_mode(make_config(source=hedef), "plan", hedef)
    assert load_config(hedef).runtime.approval_mode == "plan"


def test_izinleri_atla_kalici_yazilmaz(tmp_path):
    """Tek tuşla yanlışlıkla açılmasın diye `bypass` yalnız oturumluktur."""
    hedef = tmp_path / "c.yaml"
    with pytest.raises(ValueError, match="oturum"):
        write_approval_mode(make_config(source=hedef), "bypass", hedef)


def test_zeka_motoru_secimi_kalici_yazilir(tmp_path):
    state, hedef = _state(tmp_path)
    assert intelligence.apply(state, {"anahtar": "motor", "deger": "fusion"})["ok"]
    assert state.engine is Engine.FUSION
    assert load_config(hedef).runtime.engine == "fusion"


def test_yeni_oturum_kayitli_motor_ve_izin_modunu_alir(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)
    write_engine(config, "fusion", hedef)
    write_approval_mode(config, "edits", hedef)
    yeni = ReplState.from_runtime_config(
        load_config(hedef), memory=null_memory(), root=tmp_path, home=tmp_path
    )
    assert yeni.engine is Engine.FUSION
    assert yeni.approval is ApprovalMode.ACCEPT_EDITS


def test_bozuk_kayitli_deger_varsayilana_duser(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  engine: yok\n  approval_mode: yok\n", encoding="utf-8")
    yeni = ReplState.from_runtime_config(
        load_config(hedef), memory=null_memory(), root=tmp_path, home=tmp_path
    )
    assert yeni.engine is Engine.AGENT and yeni.approval is ApprovalMode.AUTO


def test_tum_ayarlar_birlikte_kalir_ve_birbirini_ezmez(tmp_path):
    hedef = tmp_path / "config.yaml"
    config = make_config(source=hedef)
    write_theme(config, "dark", hedef)
    write_workflow_mode(config, "always", hedef)
    write_runtime_flag(config, "self_review", True, hedef)
    write_engine(config, "fusion", hedef)
    write_approval_mode(config, "security", hedef)
    runtime = load_config(hedef).runtime
    assert (runtime.theme, runtime.workflow_mode.value, runtime.self_review) == (
        "dark",
        "always",
        True,
    )
    assert (runtime.engine, runtime.approval_mode) == ("fusion", "security")


def test_hesap_cikisi_kullanici_ayarlarini_silmez(tmp_path, monkeypatch):
    from fusion_cli.appserver.accounts import AccountService

    hedef = tmp_path / "config.yaml"
    write_engine(make_config(source=hedef), "fusion", hedef)
    prefs = tmp_path / "ui.json"
    monkeypatch.setattr(ui_prefs, "prefs_path", lambda: prefs)
    ui_prefs.save({"anahtar": "fusion.layout", "deger": "{}"})
    service = AccountService.__new__(AccountService)
    monkeypatch.setattr("fusion_cli.appserver.accounts.clear_active_account", lambda: None)
    monkeypatch.setattr("fusion_cli.appserver.accounts.forget_remembered_account", lambda: None)
    assert service.logout() == {"ok": True}
    assert load_config(hedef).runtime.engine == "fusion"
    assert ui_prefs.load()["degerler"] == {"fusion.layout": "{}"}


class TestArayuzTercihleri:
    @pytest.fixture(autouse=True)
    def _yol(self, tmp_path, monkeypatch):
        self.yol = tmp_path / "ui-prefs.json"
        monkeypatch.setattr(ui_prefs, "prefs_path", lambda: self.yol)

    def test_yaz_oku(self):
        assert ui_prefs.save({"anahtar": "fusion.sidebar.history-open.v1", "deger": "false"})["ok"]
        assert ui_prefs.load() == {
            "ok": True,
            "degerler": {"fusion.sidebar.history-open.v1": "false"},
        }

    def test_null_anahtari_siler(self):
        ui_prefs.save({"anahtar": "fusion.a", "deger": "1"})
        ui_prefs.save({"anahtar": "fusion.a", "deger": None})
        assert ui_prefs.load()["degerler"] == {}

    def test_fusion_disi_anahtar_ve_buyuk_deger_reddedilir(self):
        assert not ui_prefs.save({"anahtar": "baska.x", "deger": "1"})["ok"]
        assert not ui_prefs.save({"anahtar": "fusion.x", "deger": "a" * (ui_prefs.MAX_VALUE + 1)})[
            "ok"
        ]
        assert not ui_prefs.save({"anahtar": "fusion.x", "deger": 5})["ok"]
        assert not ui_prefs.save("x")["ok"]

    def test_bozuk_dosya_bos_sayilir(self):
        self.yol.write_text("{bozuk", encoding="utf-8")
        assert ui_prefs.load()["degerler"] == {}

    def test_dosya_json_ve_utf8(self):
        ui_prefs.save({"anahtar": "fusion.ad", "deger": "Mağaza"})
        assert json.loads(self.yol.read_text(encoding="utf-8"))["fusion.ad"] == "Mağaza"
