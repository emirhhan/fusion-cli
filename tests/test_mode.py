"""`/mode` komutu ve per-tur auto profil uygulaması.

Gerçek kademeler gerektiği için yapılandırma `load_config` ile yüklenir (varsayılan
kademeler dahil). Seçim ekranı ve konsol enjekte/yakalanır: canlı terminal olmadan
test edilir.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from fusion_cli.cli.repl import model_flows
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.loop import _apply_auto_profile
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.memory.factory import null_memory
from fusion_cli.ui import messages


@pytest.fixture
def config(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  max_tokens: 4096\n", encoding="utf-8")
    return load_config(hedef)


@pytest.fixture
def state(config, tmp_path):
    return ReplState(config=config, memory=null_memory(), root=tmp_path, home=tmp_path)


def _run(state, satir):
    name, argument = parse(satir)
    command = build_registry().get(name)
    assert command is not None, satir
    return command.handler(state, argument)


def test_mode_high_high_kademesini_uygular(state):
    _run(state, "/mode high")
    assert state.config.agent == state.config.tier_by_name("high").agent


def test_mode_max_premium_kademesine_cozulur(state):
    _run(state, "/mode max")
    assert state.config.agent == state.config.tier_by_name("premium").agent


def test_mode_auto_oturum_kipini_acar(state):
    mesaj = _run(state, "/mode auto")
    assert state.auto_profile is True
    assert mesaj == messages.MODE_AUTO_ON


def test_elle_profil_secmek_auto_kipini_kapatir(state):
    state.auto_profile = True
    _run(state, "/mode low")
    assert state.auto_profile is False


def test_bilinmeyen_profil_anlasilir_hata_verir(state):
    onceki = state.config.agent
    mesaj = _run(state, "/mode efsanevi")
    assert "efsanevi" in mesaj
    assert state.config.agent == onceki


def test_bos_mode_secim_ekranindan_vazgecmek(state, monkeypatch):
    monkeypatch.setattr(model_flows, "choose_mode", lambda config: None)
    mesaj = _run(state, "/mode")
    assert mesaj == messages.PICKER_CANCELLED
    assert state.auto_profile is False


def test_bos_mode_secim_ekranindan_auto_secmek(state, monkeypatch):
    monkeypatch.setattr(model_flows, "choose_mode", lambda config: model_flows.AUTO_CHOICE)
    _run(state, "/mode")
    assert state.auto_profile is True


def test_auto_uygulamasi_gorevden_kademe_secer(state):
    state.auto_profile = True
    console = Console(file=io.StringIO(), force_terminal=False)
    _apply_auto_profile("Tüm mimariyi yeniden tasarla", state, console)
    # "max" → premium kademesine çözülür.
    assert state.config.agent == state.config.tier_by_name("premium").agent


def test_auto_uygulamasi_gerekce_basar(state):
    state.auto_profile = True
    tampon = io.StringIO()
    console = Console(file=tampon, force_terminal=False)
    _apply_auto_profile("Dağıtık cache bug'ını çöz", state, console)
    cikti = tampon.getvalue()
    assert "auto profil" in cikti
    assert "high" in cikti


def test_auto_kapaliyken_yapilandirma_degismez(state):
    onceki = state.config.agent
    console = Console(file=io.StringIO(), force_terminal=False)
    _apply_auto_profile("Tüm mimariyi yeniden tasarla", state, console)
    assert state.config.agent == onceki


def test_mode_komutu_kayitli():
    assert build_registry().get("mode") is not None
