"""Sağlayıcı tanım kayıt defteri ve `/providers` görünümü."""

from __future__ import annotations

import pytest

from fusion_cli.config.keys import NIM_ENV, OPENROUTER_ENV
from fusion_cli.providers.registry import (
    BUILTIN_PROVIDERS,
    OfficialStatus,
    ProviderKind,
    provider_for_model,
)


def test_model_onekinden_saglayici_cozulur():
    definition = provider_for_model("openrouter/x/y:free")
    assert definition is not None
    assert definition.id == "openrouter"


def test_nim_modeli_nim_saglayicisina_cozulur():
    assert provider_for_model("nvidia_nim/nvidia/model").id == "nvidia_nim"


def test_taninmayan_onek_none_dondurur():
    # Kullanıcının yazdığı serbest uç yönetilen sağlayıcı değildir — hata değil.
    assert provider_for_model("bilinmeyen-uc/model") is None


def test_resmi_openai_onegi_taninir():
    assert provider_for_model("openai/gpt-4o").id == "openai"


def test_resmi_gemini_ve_anthropic_taninir():
    assert provider_for_model("gemini/gemini-2.0").id == "gemini"
    assert provider_for_model("anthropic/claude-sonnet-4").id == "anthropic"


def test_openrouter_aggregator_olarak_isaretli():
    definition = provider_for_model("openrouter/x/y")
    assert definition.kind is ProviderKind.AGGREGATOR
    assert definition.official_status is OfficialStatus.OFFICIAL_API


def test_yerel_saglayici_anahtarsiz_hazir():
    ollama = next(p for p in BUILTIN_PROVIDERS if p.id == "ollama")
    assert ollama.auth_env is None
    assert ollama.is_configured({}) is True


def test_anahtar_gerektiren_saglayici_bos_ortamda_hazir_degil():
    openrouter = next(p for p in BUILTIN_PROVIDERS if p.id == "openrouter")
    assert openrouter.is_configured({}) is False
    assert openrouter.is_configured({OPENROUTER_ENV: "sk-xyz"}) is True


def test_bos_anahtar_kurulu_sayilmaz():
    nim = next(p for p in BUILTIN_PROVIDERS if p.id == "nvidia_nim")
    assert nim.is_configured({NIM_ENV: "   "}) is False


def test_tum_tanimlar_benzersiz_kimlikli():
    kimlikler = [definition.id for definition in BUILTIN_PROVIDERS]
    assert len(kimlikler) == len(set(kimlikler))


# --- /providers komutu ----------------------------------------------------- #


@pytest.fixture
def state(tmp_path):
    from fusion_cli.cli.repl.state import ReplState
    from fusion_cli.memory.factory import null_memory

    from .fakes import make_config

    return ReplState(config=make_config(), memory=null_memory(), root=tmp_path)


def _run(state, satir):
    from fusion_cli.cli.repl.commands import build_registry, parse

    name, argument = parse(satir)
    return build_registry().get(name).handler(state, argument)


def test_providers_komutu_tum_saglayicilari_listeler(state, monkeypatch):
    monkeypatch.delenv(OPENROUTER_ENV, raising=False)
    monkeypatch.delenv(NIM_ENV, raising=False)
    mesaj = _run(state, "/providers")
    assert "OpenRouter" in mesaj
    assert "NVIDIA NIM" in mesaj
    assert "Ollama" in mesaj


def test_providers_kurulu_anahtari_gosterir(state, monkeypatch):
    monkeypatch.setenv(OPENROUTER_ENV, "sk-abc")
    from fusion_cli.ui import messages

    mesaj = _run(state, "/providers")
    assert messages.PROVIDERS_CONFIGURED in mesaj


# --- web-session sağlayıcı tanımları (framework düzeyi) -------------------- #


def test_web_saglayici_web_session_turunde_ve_yurutulmemis():
    from fusion_cli.providers.registry import ProviderKind, RiskLevel

    web = next(p for p in BUILTIN_PROVIDERS if p.id == "chatgpt_web")
    assert web.kind is ProviderKind.WEB_SESSION
    assert web.implemented is False
    assert web.risk_level is RiskLevel.DISABLED_BY_DEFAULT


def test_web_saglayici_model_onegi_yok_cagirilamaz():
    # Yürütücüsü olmadığı için önek boştur; hiçbir model kimliğine sahiplenmez.
    web = next(p for p in BUILTIN_PROVIDERS if p.id == "gemini_web")
    assert web.owns("gemini_web/whatever") is False


def test_providers_yurutulmemis_saglayiciyi_framework_isaretler(state):
    from fusion_cli.ui import messages

    mesaj = _run(state, "/providers")
    assert messages.PROVIDERS_FRAMEWORK in mesaj
