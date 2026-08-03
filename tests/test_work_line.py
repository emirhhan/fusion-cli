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


def test_spinner_kesme_ipucu_ve_token_okunu_gosterir():
    """Claude dizilimi: parantez içinde `↑ token` ve kesme ipucu."""
    import io

    from rich.console import Console

    from fusion_cli.ui.work import WorkState

    state = WorkState(label="hazırlanıyor…", model="nemotron", tokens=1200)
    buffer = io.StringIO()
    Console(file=buffer, force_terminal=False, width=200, no_color=True).print(state)

    cikti = buffer.getvalue()
    assert "durdurmak için Ctrl-C" in cikti
    assert "↑ 1.2k token" in cikti


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


# --------------------------------------------------------------------------- #
# Çalışma satırı ROL adını değil, gerçekten çalışan MODELİ gösterir
# --------------------------------------------------------------------------- #


def test_satirda_rol_adi_degil_model_kimligi_yazar():
    """Rol adı yapılandırmada yazan addır ve yedeğe düşülse bile değişmez."""
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    sink = WorkLineSink(satirlar.append, lambda: None)

    sink.handle(ModelCallStarted(role="agent", model="nvidia_nim/z-ai/glm-5.2", background=False))

    assert "glm-5.2" in satirlar[-1]
    assert "agent" not in satirlar[-1], "rol adı kimlik olarak kullanılmamalı"


def test_yedek_devralirsa_satir_gercek_modele_guncellenir():
    """Regresyon: yedek cevap verdiğinde ekran SEÇİLEN modeli göstermeye devam ediyordu.

    Kullanıcı bir kademe seçip başka bir modelin cevabını alıyor ve bunu hiçbir
    yerde göremiyordu; hatayı ancak cevabın niteliğinden sezebiliyordu.
    """
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    sink = WorkLineSink(satirlar.append, lambda: None)
    yedegin_cevabi = ModelResult(
        name="glm-5.2",  # rol adı: seçilen model
        model="nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b",  # gerçekte cevaplayan
        text="x",
        latency_ms=1,
        ok=True,
        usage=TokenUsage(completion_tokens=5),
    )

    sink.handle(ModelCallStarted(role="glm-5.2", model="nvidia_nim/z-ai/glm-5.2", background=False))
    sink.handle(ModelCallFinished(role="glm-5.2", result=yedegin_cevabi, background=False))

    assert "nemotron-3-ultra-550b-a55b" in satirlar[-1]
    assert "glm-5.2" not in satirlar[-1], "cevabı vermeyen model satırda kalmamalı"


def test_ayni_modelin_baska_saglayicidaki_kopyasi_ayirt_edilir():
    """Yedek çoğu zaman aynı modelin başka sağlayıcıdaki kopyasıdır.

    Yalnızca model adı gösterilseydi yedeğe düşmüş tur birincille aynı görünürdü.
    """
    from fusion_cli.cli.repl.work_line import WorkLineSink

    satirlar: list[str] = []
    sink = WorkLineSink(satirlar.append, lambda: None)
    openrouter_kopyasi = ModelResult(
        name="nemotron-super",
        model="openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        text="x",
        latency_ms=1,
        ok=True,
    )

    sink.handle(
        ModelCallStarted(
            role="nemotron-super",
            model="nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
            background=False,
        )
    )
    sink.handle(
        ModelCallFinished(role="nemotron-super", result=openrouter_kopyasi, background=False)
    )

    assert "openrouter" in satirlar[-1]
