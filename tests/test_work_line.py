"""Olay beslemeli çalışma satırı — model olaylarından metin üretir."""

from __future__ import annotations

from fusion_cli.core.events import (
    ModelCallFinished,
    ModelCallStarted,
    TurnFinished,
)
from fusion_cli.core.types import ModelResult, TokenUsage


def _bitti(tokens: int) -> ModelCallFinished:
    # TokenUsage.total_tokens bir property'dir (prompt + completion); kurucu
    # argümanı değildir. İstenen toplamı completion_tokens üzerinden veririz.
    sonuc = ModelResult(
        name="nemotron",
        model="nemotron-super",
        text="x",
        latency_ms=0,
        ok=True,
        usage=TokenUsage(completion_tokens=tokens),
    )
    return ModelCallFinished(role="nemotron", result=sonuc, background=False)


def test_model_baslayinca_calisma_satiri_guncellenir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    temizlendi: list[bool] = []
    sink = WorkLineSink(satirlar.append, lambda: temizlendi.append(True))

    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))

    assert satirlar, "başlangıçta bir çalışma satırı yayınlanmalı"
    assert "nemotron" in satirlar[-1]


def test_token_bilgisi_satira_yansir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    sink = WorkLineSink(satirlar.append, lambda: None)

    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))
    sink.handle(_bitti(1200))

    assert "1.2k" in satirlar[-1]  # format_tokens: 1200 → 1.2k


def test_arka_plan_cagrilari_yok_sayilir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    sink = WorkLineSink(satirlar.append, lambda: None)

    sink.handle(ModelCallStarted(role="judge", model="hakem", background=True))

    assert not satirlar, "arka plan çağrısı çalışma satırı yayınlamamalı"


def test_tur_bitince_satir_temizlenir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    temizlendi: list[bool] = []
    sink = WorkLineSink(lambda s: None, lambda: temizlendi.append(True))

    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))
    sink.handle(TurnFinished())

    assert temizlendi == [True]
