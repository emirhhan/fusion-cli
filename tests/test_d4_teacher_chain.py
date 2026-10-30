"""Öğretmen zinciri: aday sayısı sabitle uyumlu, çöküş görünür (A1-20, A1-21)."""

from __future__ import annotations

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.events import StatusChanged
from fusion_cli.core.types import ModelResult, ModelSpec
from fusion_cli.engines.agent import engine_tools
from fusion_cli.engines.agent.engine_tools import TEACHER_FALLBACKS, teacher_candidates

from .fakes import make_config
from .test_ask_teacher import _deps, _ogretmen, _registry


def _oturum(model: str) -> WebSessionConfig:
    return WebSessionConfig(
        model=model,
        provider=model.split("/")[0],
        transport="browser",
        login_verified=True,
        enabled=True,
    )


def test_web_yedegi_sabitten_fazla_olmaz_codex_payi_ayri_kalir(monkeypatch):
    monkeypatch.setattr("fusion_cli.providers.codex_cli.codex_ready", lambda: True)
    config = make_config(
        teacher=ModelSpec(name="ogretmen", model="gemini_web/main/auto"),
        web_sessions=(
            _oturum("gemini_web/main/auto"),
            _oturum("chatgpt_web/main/auto"),
            _oturum("claude_web/main/auto"),
        ),
    )
    from dataclasses import replace

    config = replace(config, runtime=replace(config.runtime, teacher_codex_fallback=True))

    adaylar = teacher_candidates(config, config.teacher)

    web = [a for a in adaylar if not a.model.startswith("codex_cli/")]
    assert len(web) == 1 + TEACHER_FALLBACKS
    assert any(a.model.startswith("codex_cli/") for a in adaylar)


async def test_ogretmene_ulasilamayinca_kullaniciya_gorunur_olay_yayinlanir(tmp_path, monkeypatch):
    class _Basarisiz:
        label = "sahte"

        async def complete(self, request):
            del request
            return ModelResult(
                name="o", model="sahte/o", text="", latency_ms=1, ok=False, error="oturum kilitli"
            )

    _ogretmen(monkeypatch, _Basarisiz())
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))

    sonuc = await _registry(deps).execute("ask_teacher", {"question": "s"}, deps.tool_context)

    assert sonuc.ok is False
    notlar = [e.message for e in deps.publisher.events if isinstance(e, StatusChanged)]
    assert any("Öğretmen devre dışı" in not_ and "oturum kilitli" in not_ for not_ in notlar)


async def test_toplam_sure_dolunca_yeni_aday_denenmez(tmp_path, monkeypatch):
    sorulan: list[str] = []

    class _Yavas:
        label = "sahte"

        async def complete(self, request):
            del request
            sorulan.append("x")
            return ModelResult(
                name="o", model="sahte/o", text="", latency_ms=1, ok=False, error="e"
            )

    _ogretmen(monkeypatch, _Yavas())
    deps = _deps(tmp_path, teacher=ModelSpec(name="ogretmen", model="sahte/ogretmen"))
    monkeypatch.setattr(
        engine_tools,
        "teacher_candidates",
        lambda config, teacher: [teacher, ModelSpec(name="y1", model="s/y1")],
    )
    saat = iter([0.0, 10_000.0, 10_001.0, 10_002.0])
    monkeypatch.setattr(engine_tools, "_monotonic", lambda: next(saat), raising=False)

    await _registry(deps).execute("ask_teacher", {"question": "s"}, deps.tool_context)

    assert len(sorulan) == 1
