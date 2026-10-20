"""Seçili web modeli dosya yazamıyorsa iş o tur için çırak API modeline devredilir.

Ölçüldü (30 Eylül, masaüstü): kullanıcı ChatGPT web'i seçmişti; "ayakkabisite
klasörü oluştur" isteğinde yazma araçları hiç sunulmadı ve model "bu ortamda
dosya yazma araçları yok" deyip kodu sohbete döktü. Hedef mimari: web modelleri
öğretmen, işi araç kullanabilen çırak yapar.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.models import TierSpec, WebSessionConfig
from fusion_cli.core.events import ApprenticeHandoff
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.loop import AgentDeps, run_agent

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)

_WEB = "chatgpt_web/main/auto"
_CIRAK = "nvidia_nim/cirak-model"


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self.sink = sink

    def publish(self, event: object) -> None:
        self.sink.handle(event)


def _deps(tmp_path, *, tiers=True, tool_eval_passed=False):
    cirak = ModelSpec(name="cirak", model=_CIRAK)
    config = make_config(
        agent=ModelSpec(name="secilen", model=_WEB, tags=("strict",)),
        task_model_map={},
        web_sessions=(
            WebSessionConfig(
                model=_WEB,
                provider="chatgpt_web",
                transport="browser",
                login_verified=True,
                tool_support="emulated",
                tool_eval_passed=tool_eval_passed,
            ),
        ),
        tiers=(TierSpec(name="low", label="çırak", agent=cirak, judge=cirak, candidates=(cirak,)),)
        if tiers
        else (),
    )
    sink = RecordingSink()
    deps = AgentDeps(
        config=config,
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return deps, sink


def _providers(monkeypatch, answers):
    from fusion_cli.engines.agent import loop
    from fusion_cli.providers import factory

    kullanilan: list[str] = []
    saglayicilar = {model: ScriptedProvider(list(items)) for model, items in answers.items()}

    def _build(spec, **_kwargs):
        kullanilan.append(spec.model)
        return saglayicilar[spec.model]

    monkeypatch.setattr(loop, "build_provider", _build)
    monkeypatch.setattr(factory, "build_provider", _build)
    return kullanilan, saglayicilar


async def test_yazamayan_web_modeli_yerine_cirak_dosyayi_yazar(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path)
    kullanilan, _ = _providers(
        monkeypatch,
        {
            _CIRAK: [
                model_result(
                    tool_calls=(
                        tool_call(
                            "write_file", path="ayakkabisite/index.html", content="<h1>x</h1>"
                        ),
                    )
                ),
                model_result("Klasör ve sayfa oluşturuldu."),
            ],
            _WEB: [model_result('{"bulgular": []}')] * 4,
        },
    )

    await run_agent("ayakkabisite adlı klasör oluştur ve içine index.html yaz", deps)

    assert (tmp_path / "ayakkabisite" / "index.html").read_text() == "<h1>x</h1>"
    assert _CIRAK in kullanilan
    devir = [event for event in sink.events if isinstance(event, ApprenticeHandoff)]
    assert devir and devir[0].selected_model == _WEB and devir[0].apprentice_model == _CIRAK


async def test_yazabilen_secimde_devir_yapilmaz(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path, tool_eval_passed=True)
    _providers(monkeypatch, {_WEB: [model_result("Tamam.")]})

    await run_agent("Merhaba", deps)

    assert not any(isinstance(event, ApprenticeHandoff) for event in sink.events)


async def test_cirak_kademesi_yoksa_eski_davranis_korunur(monkeypatch, tmp_path) -> None:
    deps, sink = _deps(tmp_path, tiers=False)
    deps.config = replace(deps.config)
    _providers(monkeypatch, {_WEB: [model_result("Yazamıyorum.")] * 3})

    await run_agent("ayakkabisite adlı klasör oluştur ve içine index.html yaz", deps)

    assert not any(isinstance(event, ApprenticeHandoff) for event in sink.events)
