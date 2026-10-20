"""Yedek zinciri: model düşünce/bağlam taşınca çalışan bir modele geçilir."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from fusion_cli.config.loader import load_config
from fusion_cli.core.types import (
    CompletionRequest,
    Message,
    ModelResult,
    ModelSpec,
    StreamDone,
    StreamItem,
    TextChunk,
    is_unavailable_error,
)
from fusion_cli.providers.chain import FallbackProvider
from fusion_cli.providers.fallback_plan import live_fallbacks

ISTEK = CompletionRequest((Message("user", "x"),), 0.0, 10, 5)


class Sahte:
    def __init__(self, ad: str, sonuc: ModelResult) -> None:
        self.label = ad
        self._sonuc = sonuc

    async def complete(self, request: CompletionRequest) -> ModelResult:
        return self._sonuc

    async def stream(self, request: CompletionRequest) -> AsyncIterator[StreamItem]:
        if self._sonuc.text:
            yield TextChunk(self._sonuc.text)
        yield StreamDone(self._sonuc)


def _sonuc(model: str, *, ok: bool, text: str = "", error: str | None = None) -> ModelResult:
    return ModelResult(name="r", model=model, text=text, latency_ms=1, ok=ok, error=error)


def _zincir(birincil: ModelResult, yedek: ModelResult, *, strict: bool) -> FallbackProvider:
    return FallbackProvider(
        [Sahte("a", birincil), Sahte("b", yedek)], role="r", only_when_unavailable=strict
    )


def test_katı_modelde_bagi_kopuk_sunucu_yedege_gecer() -> None:
    sonuc = asyncio.run(
        _zincir(
            _sonuc("a", ok=False, error="ConnectError: connection refused"),
            _sonuc("b", ok=True, text="tamam"),
            strict=True,
        ).complete(ISTEK)
    )
    assert sonuc.ok and sonuc.text == "tamam"


def test_baglam_tasmasi_yedege_gecirir_ve_kalici_hata_sayilir() -> None:
    hata = "ContextWindowExceededError: prompt is too long for the context length"
    assert is_unavailable_error(hata)
    sonuc = asyncio.run(
        _zincir(
            _sonuc("a", ok=False, error=hata), _sonuc("b", ok=True, text="yedek"), strict=True
        ).complete(ISTEK)
    )
    assert sonuc.text == "yedek"


def test_katı_modelde_kotu_ama_gecerli_cevap_yedege_gecmez() -> None:
    sonuc = asyncio.run(
        _zincir(
            _sonuc("a", ok=True, text="cevap"), _sonuc("b", ok=True, text="yedek"), strict=True
        ).complete(ISTEK)
    )
    assert sonuc.text == "cevap"


YAML = """\
agent:
  name: s
  model: ollama_chat/q:9b
  fallback: [nvidia_nim/x/olu]
judge: {name: s, model: ollama_chat/q:9b}
candidates: [{name: s, model: ollama_chat/q:9b}]
task_model_map: {general: s, code: s, reasoning: s, agent: s}
web_sessions:
- {model: gemini_web/main/auto, provider: gemini_web, account: main, transport: browser,
   login_verified: true, tool_eval_passed: true, enabled: true}
- {model: chatgpt_web/main/auto, provider: chatgpt_web, account: main, transport: browser,
   login_verified: true, tool_eval_passed: false, enabled: true}
"""


def _dogrulanmis(config):
    """Yükleyici profil yoksa `login_verified`'ı düşürür; testte açıkça işaretle."""
    from dataclasses import replace

    oturumlar = tuple(replace(item, login_verified=True) for item in config.web_sessions)
    return replace(config, web_sessions=oturumlar)


def _yalniz_gemini_gecer(monkeypatch) -> None:
    class _Karar:
        def __init__(self, ok: bool) -> None:
            self.ok = ok

    monkeypatch.setattr(
        "fusion_cli.providers.fallback_plan.mutation_policy_for_model",
        lambda _config, model: _Karar(model.startswith("gemini_web/")),
    )


def test_olu_yedek_ayiklanir_arac_gecen_web_oturumu_eklenir(tmp_path: Path, monkeypatch) -> None:
    _yalniz_gemini_gecer(monkeypatch)

    class _Anahtarsiz:
        nim = None
        openrouter = None

    monkeypatch.setattr("fusion_cli.providers.fallback_plan.detect", lambda: _Anahtarsiz())
    yol = tmp_path / "c.yaml"
    yol.write_text(YAML, encoding="utf-8")
    config = _dogrulanmis(load_config(yol))
    spec: ModelSpec = live_fallbacks(config.agent, config)
    assert "nvidia_nim/x/olu" not in spec.fallback
    assert spec.fallback == ("gemini_web/main/auto",)


def test_web_yedegi_kapatilabilir(tmp_path: Path, monkeypatch) -> None:
    from dataclasses import replace

    _yalniz_gemini_gecer(monkeypatch)
    yol = tmp_path / "c.yaml"
    yol.write_text(YAML, encoding="utf-8")
    config = _dogrulanmis(load_config(yol))
    kapali = replace(config, runtime=replace(config.runtime, auto_web_fallback=False))
    assert live_fallbacks(kapali.agent, kapali).fallback == ()
