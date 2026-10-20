"""Oturum akışı — fusion motoru uçtan uca, ağ olmadan."""

from __future__ import annotations

import json
from dataclasses import replace

from fusion_cli.cli import session
from fusion_cli.core.events import ErrorOccurred, FusionCompleted, TurnFinished, TurnOutcome
from fusion_cli.core.types import ModelSpec, VerdictSource
from fusion_cli.engines.fusion import engine as fusion_engine

from .fakes import FakeProvider, RecordingSink, make_config, patch_providers


def _hakem(winner):
    return FakeProvider("hakem", chunks=(json.dumps({"winner": winner, "scores": {}}),))


def _kur(monkeypatch, saglayicilar):
    patch_providers(monkeypatch, fusion_engine, saglayicilar)


async def test_basarili_tur_fusion_sonucu_olayi_yayinlar(monkeypatch):
    _kur(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A",)),
            "b": FakeProvider("b", chunks=("B",)),
            "c": FakeProvider("c", chunks=("C",)),
            "hakem": _hakem("a"),
        },
    )
    sink = RecordingSink()

    result = await session.run_task("gorev", make_config(), sinks=(sink,), synthesis=False)

    assert result.source is VerdictSource.JUDGE
    tamamlanan = [event for event in sink.events if isinstance(event, FusionCompleted)]
    assert len(tamamlanan) == 1
    assert tamamlanan[0].result.winner == "a"
    assert isinstance(sink.events[-1], TurnFinished)
    assert any(
        isinstance(event, TurnOutcome) and event.status == "completed" for event in sink.events
    )


async def test_cevapsiz_tur_hata_olayi_yayinlar(monkeypatch):
    _kur(
        monkeypatch,
        {
            "a": FakeProvider("a", ok=False, error="503"),
            "b": FakeProvider("b", ok=False, error="503"),
            "c": FakeProvider("c", ok=False, error="503"),
            "hakem": _hakem("a"),
        },
    )
    sink = RecordingSink()

    result = await session.run_task("gorev", make_config(), sinks=(sink,))

    assert result.source is VerdictSource.NONE
    hatalar = [event for event in sink.events if isinstance(event, ErrorOccurred)]
    assert hatalar and hatalar[0].fatal
    assert not any(isinstance(event, FusionCompleted) for event in sink.events)


async def test_hiz_siniri_ozel_mesaj_uretir(monkeypatch):
    _kur(
        monkeypatch,
        {
            "a": FakeProvider("a", ok=False, error="429 rate limit"),
            "b": FakeProvider("b", ok=False, error="429 rate limit"),
            "c": FakeProvider("c", ok=False, error="429 rate limit"),
            "hakem": _hakem("a"),
        },
    )
    sink = RecordingSink()

    await session.run_task("gorev", make_config(), sinks=(sink,))

    hata = next(event for event in sink.events if isinstance(event, ErrorOccurred))
    assert "kota" in hata.message.lower()
    assert any(isinstance(event, TurnOutcome) and event.status == "failed" for event in sink.events)


async def test_gorev_tipi_motora_gecirilir(monkeypatch):
    _kur(
        monkeypatch,
        {
            "a": FakeProvider("a", chunks=("A",)),
            "b": FakeProvider("b", chunks=("B",)),
            "c": FakeProvider("c", chunks=("C",)),
            "hakem": _hakem("c"),
        },
    )
    sink = RecordingSink()

    result = await session.run_task(
        "gorev", make_config(), sinks=(sink,), task_type="code", synthesis=False
    )

    assert result.task_type == "code"


def test_istek_yapilandirmadaki_calisma_zamani_ayarlarini_kullanir():
    request = session.build_request("selam", make_config())

    assert request.max_tokens == 32
    assert request.timeout_s == 5.0
    assert request.messages[0].content == "selam"


async def test_model_on_kontrol_hatasi_turu_basarisiz_sonucla_kapatir(tmp_path):
    config = replace(
        make_config(),
        agent=ModelSpec("web", "gemini_web/main/auto", tags=("strict",)),
        mcp_servers=(),
    )
    sink = RecordingSink()

    outcome = await session.run_agent_task(
        "Ekteki resmi incele",
        config,
        sinks=(sink,),
        prompter_factory=lambda _drain: None,
        root=tmp_path,
        interactive=False,
        images=("data:image/png;base64,aGVsbG8=",),
    )

    assert not outcome.ok
    assert "görsel desteği" in outcome.final_text
    assert outcome.model_calls_made == 0
    assert next(message for message in outcome.messages if message.role == "user").images
    assert isinstance(sink.events[-1], TurnFinished)
    assert sum(isinstance(event, TurnFinished) for event in sink.events) == 1
    assert any(isinstance(event, TurnOutcome) and event.status == "failed" for event in sink.events)


async def test_agent_gorevi_adim_sinirini_agent_dongusune_iletir(tmp_path, monkeypatch):
    """Masaüstündeki `/goal` turu hedef kipinin adım sınırını kaybetmemeli."""
    from types import SimpleNamespace

    yakalanan: dict = {}

    async def sahte_run_agent(task, deps, **kwargs):
        yakalanan.update(kwargs)
        return SimpleNamespace(
            ok=True,
            final_text="bitti",
            messages=[],
            budget_stopped=False,
            made_no_changes=True,
        )

    monkeypatch.setattr(session, "run_agent", sahte_run_agent)
    config = replace(make_config(), mcp_servers=())

    await session.run_agent_task(
        "hedefe git",
        config,
        sinks=(RecordingSink(),),
        prompter_factory=lambda _drain: None,
        root=tmp_path,
        interactive=False,
        step_limit=7,
    )

    assert yakalanan["step_limit"] == 7
