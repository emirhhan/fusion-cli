"""Doğrulanmamış taklit-araç modeli dosya değiştiremez.

`config/tool_policy.py` bunu belgeliyordu ama kod uygulamıyordu:

- Yetenek `ModelSpec` ETİKETLERİNDEN türetiliyordu; panelden bağlanan bir web
  oturumunun `tool_support` alanı hiç okunmuyordu. Etiketsiz model `UNKNOWN` sayılıp
  mutation'a giriyordu.
- `select_agent_spec` içindeki `strict` kısa devresi kontrolü tamamen atlıyordu:
  panelden "zorunlu model" seçmek güvenlik kapısını atlamak demekti.

Karar kullanıcıya sorulmaz — bu bir onay meselesi değil, YETENEK meselesidir.
"""

from __future__ import annotations

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.config.tool_policy import mutation_policy_for_model
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.execution_policy import policy_for

from .fakes import make_config

WEB_MODEL = "chatgpt_web/main/auto"


def _config(**session_overrides):
    alanlar = {
        "model": WEB_MODEL,
        "provider": "chatgpt_web",
        "account": "main",
        "transport": "browser",
        "tool_support": "emulated",
    }
    alanlar.update(session_overrides)
    return make_config(web_sessions=(WebSessionConfig(**alanlar),))


def test_dogrulanmamis_taklit_arac_modeli_mutation_yapamaz():
    policy = mutation_policy_for_model(_config(), WEB_MODEL)

    assert policy.ok is False
    assert "eval" in policy.reason


def test_eval_esigini_gecen_model_mutation_yapabilir():
    policy = mutation_policy_for_model(_config(tool_eval_passed=True), WEB_MODEL)

    assert policy.ok is True


def test_aracsiz_web_oturumu_mutation_yapamaz():
    policy = mutation_policy_for_model(_config(tool_support="none"), WEB_MODEL)

    assert policy.ok is False
    assert "araç desteği yok" in policy.reason


def test_web_oturumu_olmayan_model_etkilenmez():
    """API modelleri bu kapıdan geçmez; davranışları birebir korunur."""
    assert mutation_policy_for_model(_config(), "nvidia_nim/nvidia/nemotron").ok is True


def test_strict_secim_guvenlik_kapisini_atlayamaz():
    """Panelden "zorunlu model" seçmek yetenek kapısını devre dışı bırakamaz."""
    config = _config()
    strict_spec = ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))

    execution = policy_for(config, strict_spec, TaskKind.FEATURE, "dosyayı düzelt")

    assert execution.allow_mutation is False
    assert execution.mutation_block_reason


def test_eval_gecmisse_yurutme_politikasi_izin_verir():
    config = _config(tool_eval_passed=True)
    spec = ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))

    execution = policy_for(config, spec, TaskKind.FEATURE, "dosyayı düzelt")

    assert execution.allow_mutation is True


def test_api_modeli_varsayilan_olarak_mutation_yapabilir():
    config = make_config()
    spec = ModelSpec(name="agent", model="nvidia_nim/x")

    execution = policy_for(config, spec, TaskKind.FEATURE, "dosyayı düzelt")

    assert execution.allow_mutation is True
