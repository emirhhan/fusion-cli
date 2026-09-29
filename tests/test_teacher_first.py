"""Öğretmenin ilk planı ile çırağın aynı turda işe başlaması."""

from __future__ import annotations

import asyncio
from dataclasses import replace

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.events import StatusChanged, TeacherTaskClassified
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.types import ModelSpec
from fusion_cli.engines.agent import loop as agent_loop
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


class _Publisher:
    def __init__(self, sink: RecordingSink) -> None:
        self.sink = sink

    def publish(self, event: object) -> None:
        self.sink.handle(event)


def _setup(
    monkeypatch, tmp_path, *, verified: bool = True, teacher_answers=None, apprentice_answers=None
):
    from fusion_cli.engines.agent import loop
    from fusion_cli.providers import factory

    teacher = ScriptedProvider(
        teacher_answers
        or [
            model_result(
                '{"adimlar":["Dosyayı oku","Düzeltmeyi doğrula"],"dosyalar":["src/app.py"],'
                '"riskler":[],"yapilamayanlar":[],"dogrulama":["pytest çalıştır"]}'
            )
        ]
    )
    apprentice = ScriptedProvider(
        apprentice_answers or [model_result("İşi inceledim; henüz değişiklik yapmadım.")]
    )

    def _teacher_provider(_spec, **_kwargs):
        return teacher

    def _apprentice_provider(_spec, **_kwargs):
        return apprentice

    monkeypatch.setattr(factory, "build_provider", _teacher_provider)
    monkeypatch.setattr(loop, "build_provider", _apprentice_provider)
    sink = RecordingSink()
    config = make_config(
        teacher=ModelSpec(name="ogretmen", model="gemini_web/main/auto"),
        web_sessions=(
            WebSessionConfig(
                model="gemini_web/main/auto",
                provider="gemini_web",
                transport="browser",
                login_verified=verified,
            ),
        ),
    )
    deps = AgentDeps(
        config=config,
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
    )
    return deps, sink, teacher, apprentice


async def test_ogretmen_plani_ciraktan_once_gorev_listesine_ve_baglama_girer(
    monkeypatch, tmp_path
) -> None:
    deps, sink, teacher, apprentice = _setup(monkeypatch, tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='ornek-proje'\nprivate_setting='hassas_deger'\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "token = 'ozel_anahtar'\ndef calculate_total():\n    return 1\n", encoding="utf-8"
    )

    await run_agent("src/app.py dosyasındaki hatayı düzelt", deps)

    assert teacher.calls == 1
    assert apprentice.calls >= 1
    assert [item.content for item in deps.tool_context.todos.items] == [
        "Dosyayı oku",
        "Düzeltmeyi doğrula",
    ]
    assert any("Dosyayı oku" in message.content for message in apprentice.seen_messages[0])
    assert any(isinstance(event, TeacherTaskClassified) for event in sink.events)
    assert "pyproject.toml" in teacher.seen_messages[0][0].content
    assert "hassas_deger" not in teacher.seen_messages[0][0].content
    assert "ozel_anahtar" not in teacher.seen_messages[0][0].content
    assert "calculate_total" in teacher.seen_messages[0][0].content


async def test_dogrulanmamis_oturumda_cirak_tek_basina_ilerler(monkeypatch, tmp_path) -> None:
    deps, _sink, teacher, apprentice = _setup(monkeypatch, tmp_path, verified=False)

    await run_agent("src/app.py dosyasındaki hatayı düzelt", deps)

    assert teacher.calls == 0
    assert apprentice.calls >= 1


async def test_ogretmen_zaman_asiminda_cirak_beklemeden_ilerler(monkeypatch, tmp_path) -> None:
    deps, _sink, teacher, apprentice = _setup(monkeypatch, tmp_path)
    deps.config = replace(deps.config, runtime=replace(deps.config.runtime, request_timeout_s=0.02))

    async def _slow_complete(_request):
        await asyncio.sleep(1)

    monkeypatch.setattr(teacher, "complete", _slow_complete)

    await asyncio.wait_for(run_agent("src/app.py dosyasındaki hatayı düzelt", deps), timeout=0.5)

    assert apprentice.calls >= 1


async def test_basit_soruda_ogretmen_cagrilmaz(monkeypatch, tmp_path) -> None:
    deps, _sink, teacher, apprentice = _setup(monkeypatch, tmp_path)

    await run_agent("Merhaba", deps)

    assert teacher.calls == 0
    assert apprentice.calls == 1


async def test_yapilamayan_is_baslamadan_alternatifiyle_bildirilir(monkeypatch, tmp_path) -> None:
    answer = model_result(
        '{"adimlar":["Taslağı hazırla"],"dosyalar":[],"riskler":[],'
        '"yapilamayanlar":[{"konu":"Story çıkartması","gerekce":"API desteklemiyor",'
        '"alternatif":"Telefona bildirim gönder"}],"dogrulama":[]}'
    )
    deps, sink, _teacher, apprentice = _setup(monkeypatch, tmp_path, teacher_answers=[answer])

    await run_agent("Instagram API ile Story çıkartması yayımlama akışını kur", deps)

    assert apprentice.calls >= 1
    assert any(
        isinstance(event, StatusChanged) and "Telefona bildirim gönder" in event.message
        for event in sink.events
    )


async def test_bozuk_plan_bir_duzeltme_isteginden_sonra_uygulanir(monkeypatch, tmp_path) -> None:
    corrected = model_result(
        '{"adimlar":["Test yaz"],"dosyalar":[],"riskler":[],"yapilamayanlar":[],"dogrulama":[]}'
    )
    deps, _sink, teacher, apprentice = _setup(
        monkeypatch, tmp_path, teacher_answers=[model_result("bozuk"), corrected]
    )

    await run_agent("src/app.py dosyasındaki hatayı düzelt", deps)

    assert teacher.calls == 2
    assert deps.tool_context.todos.items[0].content == "Test yaz"
    assert any("Test yaz" in message.content for message in apprentice.seen_messages[0])


async def test_iki_bozuk_plan_dovusunde_duz_metinle_cirak_ilerler(monkeypatch, tmp_path) -> None:
    deps, _sink, teacher, apprentice = _setup(
        monkeypatch, tmp_path, teacher_answers=[model_result("ilk not"), model_result("yine bozuk")]
    )

    await run_agent("src/app.py dosyasındaki hatayı düzelt", deps)

    assert teacher.calls == 2
    assert not deps.tool_context.todos.items
    assert any("ilk not" in message.content for message in apprentice.seen_messages[0])


async def test_dosya_degisince_ogretmen_son_denetimi_yapilir(monkeypatch, tmp_path) -> None:
    (tmp_path / "src").mkdir()
    plan = model_result(
        '{"adimlar":["Dosyayı yaz"],"dosyalar":["src/app.py"],"riskler":[],'
        '"yapilamayanlar":[],"dogrulama":["pytest çalıştır"]}'
    )
    review = model_result('{"bulgular": []}')
    deps, _sink, teacher, _apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[plan, review],
        apprentice_answers=[
            model_result(
                tool_calls=(tool_call("write_file", path="src/app.py", content="x = 1\n"),)
            ),
            model_result("Dosya yazıldı ve doğrulama durumu bildirildi."),
        ],
    )

    await run_agent("src/app.py dosyasını oluştur", deps)

    assert teacher.calls == 2
    assert "src/app.py" in teacher.seen_messages[1][0].content
    assert "bulgular" in teacher.seen_messages[1][0].content


async def test_ogretmen_bulgusu_duzeltici_tur_acar_ve_duzeltilmezse_basari_sayilmaz(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / "src").mkdir()
    plan = model_result(
        '{"adimlar":["Dosyayı yaz"],"dosyalar":[],"riskler":[],"yapilamayanlar":[],"dogrulama":[]}'
    )
    review = model_result('{"bulgular": ["Yetkili istek testi eksik"]}')
    deps, _sink, teacher, apprentice = _setup(
        monkeypatch,
        tmp_path,
        teacher_answers=[plan, review],
        apprentice_answers=[
            model_result(
                tool_calls=(tool_call("write_file", path="src/app.py", content="x = 1\n"),)
            ),
            model_result("İlk değişiklik tamamlandı."),
            model_result("Bulguya baktım ama düzeltme yapmadım."),
        ],
    )

    result = await run_agent("src/app.py dosyasını oluştur", deps)

    assert teacher.calls == 2
    assert apprentice.calls >= 3
    assert result.ok is False


def test_ayni_hata_iki_kez_yasaninca_ogretmen_nedeni_hazirlanir() -> None:
    state = agent_loop._State()
    state.repeated_failures[("write_file", "izin reddedildi")] = 2

    assert agent_loop._teacher_stall_reason(state) == "aynı araç hatası tekrarlandı"


def test_tekrar_korumasi_danismanlik_nedeni_olur() -> None:
    state = agent_loop._State()
    state.repeat_blocked = True

    assert agent_loop._teacher_stall_reason(state) == "tekrar koruması aynı okumayı engelledi"
