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

import pytest

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.config.tool_policy import mutation_policy_for_model
from fusion_cli.core.events import MutationUnavailable
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.classify import TaskKind
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.effects.detect import required_effect_for

from .fakes import AlwaysApprove, RecordingSink, ScriptedProvider, make_config, model_result


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)

WEB_MODEL = "chatgpt_web/main/auto"


def _config(**session_overrides):
    alanlar = {
        "model": WEB_MODEL,
        "provider": "chatgpt_web",
        "account": "main",
        "transport": "browser",
        "tool_support": "emulated",
    }
    config_overrides = {
        key: session_overrides.pop(key)
        for key in list(session_overrides)
        if key == "agent"
    }
    alanlar.update(session_overrides)
    return make_config(web_sessions=(WebSessionConfig(**alanlar),), **config_overrides)


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


# --- Kısıt SESSİZ kalmamalı --------------------------------------------------- #
#
# Gerçek kullanım: kullanıcı Gemini web oturumuna "arkadaki uygulamayı kapat" dedi.
# Model "böyle bir aracım yok" dedi ve HAKLIYDI — run_shell şeması ona hiç
# sunulmamıştı. Ama kısıtın nereden geldiği hiçbir yerde görünmüyordu ve kullanıcı
# Fusion'ı arızalı sandı.


async def test_arka_plan_uygulamasini_kapatma_gercek_eylem_sayilir():
    """'kapat' hiçbir desende yoktu; istek sohbet sanılıyordu."""
    assert required_effect_for("arkada çalışan bir uygulamayı kapat") == "shell_action"
    assert required_effect_for("arkaplandaki uygulamayı kapat") == "shell_action"
    assert required_effect_for("uygulamayı sonlandır") == "shell_action"


async def test_dosya_ya_da_pencere_kapatmak_sistem_eylemi_sayilmaz():
    """Aşırı yakalama, sohbeti araç turuna çevirirdi."""
    assert required_effect_for("bu dosyayı kapat") is None
    assert required_effect_for("pencereyi kapat") is None
    assert required_effect_for("tarayıcıyı kapatma") is None


async def test_yapilamayacak_eylemde_tur_model_cagirmadan_biter(tmp_path):
    """Model çağrısı harcanmaz ve kullanıcıya ne yapacağı söylenir."""
    sink = RecordingSink()
    cagrilar = {"sayi": 0}

    class _Sayan:
        label = "gemini"

        async def stream(self, request):
            cagrilar["sayi"] += 1
            raise AssertionError("model hiç çağrılmamalıydı")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kw: _Sayan())
    try:
        deps = AgentDeps(
            config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
            publisher=_Publisher(sink),
            policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
            tool_context=ToolContext(root=tmp_path),
        )
        sonuc = await run_agent("arkadaki uygulamayı kapat", deps)
    finally:
        monkeypatch.undo()

    assert cagrilar["sayi"] == 0
    assert not sonuc.ok
    assert "Araç yeteneğini ölç" in sonuc.final_text
    assert "Hiçbir değişiklik yapılmadı" in sonuc.final_text
    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is True


async def test_salt_okunur_kip_sohbet_turunda_da_bildirilir(tmp_path, monkeypatch):
    """Görev eylem istemese bile kullanıcı salt-okunur kipte olduğunu görmeli."""
    sink = RecordingSink()
    monkeypatch.setattr(
        agent_loop,
        "build_provider",
        lambda spec, **kw: ScriptedProvider([model_result("liste değiştirilebilir.")]),
    )
    deps = AgentDeps(
        config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    await run_agent("liste ile demet farkı nedir", deps)

    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is False


# --- Ölçüm sonucu ve tür temelli engelleme ------------------------------------ #


async def test_kod_duzeltme_gorevi_mutation_kapaliyken_erken_biter(tmp_path, monkeypatch):
    """Metinden effect çıkarılamasa bile BUGFIX türü değişiklik ister.

    Gerçek koşu: "envanter.py'deki hataları düzelt ve eksik dogrulama modülünü yaz"
    hiçbir effect desenine uymuyordu; tur salt-okunur kipte beş çağrı harcayıp
    hiçbir şey yapamadan bitti.
    """
    sink = RecordingSink()

    class _Patlayan:
        label = "web"

        async def stream(self, request):
            raise AssertionError("model hiç çağrılmamalıydı")

    monkeypatch.setattr(agent_loop, "build_provider", lambda spec, **kw: _Patlayan())
    deps = AgentDeps(
        config=_config(agent=ModelSpec(name="web", model=WEB_MODEL, tags=("strict",))),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )

    sonuc = await run_agent(
        "envanter.py'deki hataları düzelt ve eksik dogrulama modülünü yaz", deps
    )

    assert not sonuc.ok
    assert "Araç yeteneğini ölç" in sonuc.final_text
    olay = next(e for e in sink.events if isinstance(e, MutationUnavailable))
    assert olay.blocking is True
