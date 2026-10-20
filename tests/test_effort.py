"""`/effort` komutu ve reasoning_effort yapılandırma yüklemesi."""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl import model_flows
from fusion_cli.cli.repl.commands import build_registry, parse
from fusion_cli.cli.repl.state import ReplState
from fusion_cli.config.loader import load_config
from fusion_cli.core.errors import ConfigError
from fusion_cli.core.reasoning import ReasoningEffort
from fusion_cli.memory.factory import null_memory


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


# --- yapılandırma yüklemesi (generic Enum desteği) ------------------------- #


def test_varsayilan_effort_auto(config):
    assert config.runtime.reasoning_effort is ReasoningEffort.AUTO


def test_kullanici_effort_yukler(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  reasoning_effort: high\n", encoding="utf-8")
    assert load_config(hedef).runtime.reasoning_effort is ReasoningEffort.HIGH


def test_gecersiz_effort_anlasilir_hata(tmp_path):
    hedef = tmp_path / "config.yaml"
    hedef.write_text("runtime:\n  reasoning_effort: efsanevi\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="geçersiz değer"):
        load_config(hedef)


# --- /effort komutu -------------------------------------------------------- #


def test_effort_high_uygulanir(state):
    _run(state, "/effort high")
    assert state.config.runtime.reasoning_effort is ReasoningEffort.HIGH


def test_effort_xhigh_indirgeme_bildirir(state):
    mesaj = _run(state, "/effort xhigh")
    assert state.config.runtime.reasoning_effort is ReasoningEffort.XHIGH
    assert "high" in mesaj


def test_effort_bilinmeyen_seviye_hata(state):
    onceki = state.config.runtime.reasoning_effort
    mesaj = _run(state, "/effort efsanevi")
    assert "geçersiz" in mesaj.lower() or "efsanevi" in mesaj
    assert state.config.runtime.reasoning_effort is onceki


def test_effort_secim_ekranindan_vazgecmek(state, monkeypatch):
    monkeypatch.setattr(model_flows, "choose_effort", lambda: None)
    from fusion_cli.ui import messages

    assert _run(state, "/effort") == messages.PICKER_CANCELLED


def test_effort_mode_dan_bagimsiz(state):
    # Effort değiştirmek kademeyi (mode) değiştirmez.
    onceki_agent = state.config.agent
    _run(state, "/effort high")
    assert state.config.agent == onceki_agent
