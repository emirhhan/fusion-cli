"""Yönlendirme modele bırakılır: kelime sınıflandırıcısı karar yolunda değildir.

Ölçülen hata (B2): oturumun ilk mesajı "CSV export özelliği ekle ve testlerini yaz"
iken sonraki "Tamam yaz" mesajı, geçmişle birleştirilip FEATURE sayıldı ve plan
motoruna girdi — iki kelimelik bir onay 34 saniye süren bir plan koşusu üretti.

Ölçülen hata (A5/B5): görev türüne bakılarak ders ve beceri metinleri sistem
mesajına kendiliğinden basılıyordu; yanlış tür yanlış uzmanlığı bağlama sokuyordu.

Hedef: tek ReAct döngüsü varsayılandır. Plan motoru yalnız `workflow_mode: always`
ya da kullanıcı `/plan-yurut` seçtiğinde çalışır; bütçe, bağlam ve araç şeması görev
türünden bağımsızdır; ders ve beceriler modelin isteğiyle (araçla) gelir.
"""

from __future__ import annotations

import textwrap

from fusion_cli.cli.repl import macros
from fusion_cli.config.loader import load_config
from fusion_cli.core.events import CapabilityActivated, ExecutionRouteSelected
from fusion_cli.core.execution_mode import ExecutionMode
from fusion_cli.core.memory import Lesson, LessonKind
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import Message, ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.execution_policy import policy_for
from fusion_cli.engines.agent.loop import AgentDeps, AgentOutcome, _permitted, run_agent
from fusion_cli.tools import build_registry
from fusion_cli.tools.capabilities import CapabilityRegistry

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

WEB_MODEL = "gemini_web/main/auto"


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


def _deps(tmp_path, sink, **extra):
    config_args = extra.pop("config_args", {})
    return AgentDeps(
        config=make_config(**config_args),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        **extra,
    )


def _kur(monkeypatch, provider):
    def _build(*args, **kwargs):
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)
    return provider


class _PlanCasusu:
    """`run_execution_plan` yerine geçer; çağrıldığı her görevi ve bağlamı kaydeder."""

    def __init__(self):
        self.cagrilar: list[tuple[str, dict[str, object]]] = []

    async def __call__(self, task, deps, run_agent, **kwargs):
        del deps, run_agent
        self.cagrilar.append((task, kwargs))
        return AgentOutcome(final_text="planlı sonuç", messages=[])


def _patlayan_plan(monkeypatch):
    async def _patla(*args, **kwargs):
        raise AssertionError("plan motoru varsayılan yolda çağrılmamalı")

    monkeypatch.setattr(agent_loop, "run_execution_plan", _patla)


def _urun_varsayilani() -> ExecutionMode:
    """Ürünün gerçek varsayılanı; `make_config` testlerde OFF'a sabitler."""
    return load_config().runtime.workflow_mode


def _rota(sink) -> list[str]:
    return [event.route for event in sink.events if isinstance(event, ExecutionRouteSelected)]


# --------------------------------------------------------------------------- #
# Rota
# --------------------------------------------------------------------------- #


async def test_kisa_onay_mesaji_plan_motoruna_girmez(monkeypatch, tmp_path):
    """B2'nin birebir yeniden üretimi: onay mesajı ilk görevin türünü miras almaz."""
    sink = RecordingSink()
    _patlayan_plan(monkeypatch)
    provider = _kur(monkeypatch, ScriptedProvider([model_result("Tamam.")]))
    gecmis = [
        Message("system", "sistem"),
        Message("user", "CSV export özelliği ekle ve testlerini yaz"),
        Message("assistant", "Ekledim ve testlerini yazdım."),
    ]
    deps = _deps(tmp_path, sink, config_args={"runtime": {"workflow_mode": _urun_varsayilani()}})

    sonuc = await run_agent("Tamam yaz", deps, history=gecmis)

    assert sonuc.final_text == "Tamam."
    assert provider.calls == 1
    assert _rota(sink) == ["fast"]


async def test_karmasik_gorev_varsayilan_olarak_tek_dongude_kalir(monkeypatch, tmp_path):
    sink = RecordingSink()
    _patlayan_plan(monkeypatch)
    _kur(monkeypatch, ScriptedProvider([model_result("Düzelttim.")]))
    deps = _deps(tmp_path, sink, config_args={"runtime": {"workflow_mode": _urun_varsayilani()}})

    await run_agent("hatayı düzelt, refactor et ve testleri güncelle", deps)

    assert _rota(sink) == ["fast"]


async def test_workflow_mode_always_plan_motorunu_calistirir(monkeypatch, tmp_path):
    """Plan motoru kök konuşmayı alır: sistem + önceki sohbet + bu turun mesajı."""
    sink = RecordingSink()
    casus = _PlanCasusu()
    monkeypatch.setattr(agent_loop, "run_execution_plan", casus)
    gecmis = [
        Message("system", "eski sistem"),
        Message("user", "Gizli kelime MAVİ-KEDİ, sakla."),
        Message("assistant", "Sakladım."),
    ]
    deps = _deps(tmp_path, sink, config_args={"runtime": {"workflow_mode": ExecutionMode.ALWAYS}})

    sonuc = await run_agent("Bu projeye X fonksiyonunu ekle", deps, history=gecmis)

    assert sonuc.final_text == "planlı sonuç"
    assert _rota(sink) == ["workflow"]
    gorev, kwargs = casus.cagrilar[0]
    assert gorev == "Bu projeye X fonksiyonunu ekle"
    konusma = kwargs["conversation"]
    assert isinstance(konusma, list)
    assert konusma[0].role == "system"
    assert [m.role for m in konusma].count("system") == 1
    assert any(m.content == "Gizli kelime MAVİ-KEDİ, sakla." for m in konusma)
    assert konusma[-1] == Message("user", "Bu projeye X fonksiyonunu ekle")


async def test_kullanici_plan_yurut_secince_plan_motoru_calisir(monkeypatch, tmp_path):
    sink = RecordingSink()
    casus = _PlanCasusu()
    monkeypatch.setattr(agent_loop, "run_execution_plan", casus)
    deps = _deps(tmp_path, sink, config_args={"runtime": {"workflow_mode": ExecutionMode.OFF}})

    await run_agent("merhaba dünyayı yazdır", deps, workflow=True)

    assert [gorev for gorev, _ in casus.cagrilar] == ["merhaba dünyayı yazdır"]
    assert _rota(sink) == ["workflow"]
    makro = macros.get("plan-yurut")
    assert makro is not None
    assert macros.mode_workflow(makro.mode) is True
    assert macros.mode_workflow(macros.Mode.NONE) is False


def test_eski_auto_ayari_off_olarak_yuklenir(tmp_path):
    yol = tmp_path / "config.yaml"
    yol.write_text("runtime:\n  workflow_mode: auto\n", encoding="utf-8")

    config = load_config(yol)

    assert config.runtime.workflow_mode is ExecutionMode.OFF


# --------------------------------------------------------------------------- #
# Politika
# --------------------------------------------------------------------------- #


def _web_config():
    return make_config(
        agent=ModelSpec(name="agent", model=WEB_MODEL),
        task_model_map={},
    )


def test_yurutme_politikasi_gorev_turune_bakmaz():
    config = _web_config()
    sade = policy_for(config, config.agent, "merhaba dünyayı açıkla")
    kapsamli = policy_for(config, config.agent, "tüm projeyi kapsamlı refactor et")

    assert sade.max_model_calls == kapsamli.max_model_calls
    assert sade.max_tool_rounds == kapsamli.max_tool_rounds
    assert sade.total_timeout_s == kapsamli.total_timeout_s
    assert sade.idle_timeout_s == kapsamli.idle_timeout_s


def test_duzenleme_semasi_tum_saglayicilarda_ayni():
    config = _web_config()
    api = policy_for(config, ModelSpec(name="agent", model="sahte/agent"), "dosyayı düzelt")
    web = policy_for(config, config.agent, "dosyayı düzelt")
    registry = build_registry()

    api_araclari = _permitted(None, registry, api) or set()
    web_araclari = _permitted(None, registry, web) or set()

    duzenleme = {"edit_file", "multi_edit", "write_file"}
    assert duzenleme <= api_araclari
    assert duzenleme <= web_araclari
    assert "replace_range" not in api_araclari | web_araclari
    assert api_araclari == web_araclari


# --------------------------------------------------------------------------- #
# Bağlam
# --------------------------------------------------------------------------- #


def _godot_becerisi(home):
    klasor = home / ".claude" / "skills" / "godot"
    klasor.mkdir(parents=True)
    (klasor / "SKILL.md").write_text(
        textwrap.dedent(
            """\
            ---
            name: godot
            description: Godot scene debugging error handling tscn gdscript
            ---
            GODOT-BECERI-GOVDESI: sahneleri .tscn biçiminde düzenle.
            """
        ),
        encoding="utf-8",
    )


async def test_beceri_metni_kendiliginden_baglama_girmez(monkeypatch, tmp_path):
    sink = RecordingSink()
    home = tmp_path / "home"
    _godot_becerisi(home)
    provider = _kur(monkeypatch, ScriptedProvider([model_result("Düzelttim.")]))
    deps = _deps(
        tmp_path,
        sink,
        home=home,
        capabilities=CapabilityRegistry(home, tmp_path),
    )

    await run_agent("godot sahnesini düzelt", deps)

    sistem = provider.seen_messages[0][0]
    assert sistem.role == "system"
    assert "GODOT-BECERI-GOVDESI" not in sistem.content
    assert not [e for e in sink.events if isinstance(e, CapabilityActivated)]
    sunulan = {sema["function"]["name"] for sema in provider.seen_requests[0]}
    assert {"find_skill", "read_skill"} <= sunulan


class _SayanDersBellegi:
    def __init__(self):
        self.recall_cagrilari: list[str] = []
        self._ders = Lesson(text="Godot'ta res:// yolunu kullanma.", kind=LessonKind.MISTAKE)

    def add(self, lesson):
        return True

    def recall(self, task, limit=4, *, scope=None, workspace=None, tags=()):
        self.recall_cagrilari.append(task)
        return (self._ders,)

    def reinforce(self, texts, *, success):
        return 0

    def all(self):
        return ()

    def count(self):
        return 1


async def test_dersler_kendiliginden_hatirlanmaz_ama_aracla_istenebilir(monkeypatch, tmp_path):
    sink = RecordingSink()
    bellek = _SayanDersBellegi()

    async def _ders_cikarma(*args, **kwargs):
        return ()

    monkeypatch.setattr(agent_loop.learning_steps.learning, "extract_lessons", _ders_cikarma)
    provider = _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(tool_calls=(tool_call("recall_lessons", query="godot yolları"),)),
                model_result("Hatırladım."),
            ]
        ),
    )
    deps = _deps(
        tmp_path,
        sink,
        lessons=bellek,
        config_args={"runtime": {"lessons": True}},
    )

    await run_agent("godot sahnesini düzelt", deps)

    # Tur başında bellek sorgulanmaz; tek sorgu modelin araç çağrısından gelir.
    assert bellek.recall_cagrilari == ["godot yolları"]
    assert "res://" not in provider.seen_messages[0][0].content
    arac_sonucu = [m for m in provider.seen_messages[1] if m.role == "tool"]
    assert arac_sonucu and "res://" in arac_sonucu[-1].content


def _kodlu_proje(tmp_path):
    (tmp_path / "hesap.py").write_text("def topla(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "rapor.py").write_text(
        "from hesap import topla\n\n\ndef ozet(x):\n    return topla(x, 1)\n", encoding="utf-8"
    )


async def test_depo_haritasi_gorev_turunden_bagimsiz_ve_sohbette_yok(monkeypatch, tmp_path):
    _kodlu_proje(tmp_path)
    provider = _kur(
        monkeypatch, ScriptedProvider([model_result("Merhaba!"), model_result("Merhaba!")])
    )

    await run_agent("merhaba", _deps(tmp_path, RecordingSink()))
    await run_agent("merhaba", _deps(tmp_path, RecordingSink()), chat_mode=True)

    kod_sistemi = provider.seen_messages[0][0].content
    sohbet_sistemi = provider.seen_messages[1][0].content
    assert "Depo haritası" in kod_sistemi and "topla" in kod_sistemi
    assert "Depo haritası" not in sohbet_sistemi
