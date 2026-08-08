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

    sink = WorkLineSink()

    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))

    assert sink.render(), "çalışan çağrı varken satır üretilmeli"
    assert "nemotron" in sink.render()


def test_token_bilgisi_satira_yansir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    sink = WorkLineSink()

    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))
    sink.handle(_bitti(1200))

    assert "1.2k" in sink.render()  # format_tokens: 1200 → 1.2k


def test_arka_plan_cagrilari_yok_sayilir():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    sink = WorkLineSink()

    sink.handle(ModelCallStarted(role="judge", model="hakem", background=True))

    assert sink.render() == "", "arka plan çağrısı çalışma satırı üretmemeli"


def test_tur_bitince_satir_kaybolur():
    from fusion_cli.cli.repl.work_line import WorkLineSink

    sink = WorkLineSink()

    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))
    sink.handle(TurnFinished())

    assert sink.render() == ""


# --------------------------------------------------------------------------- #
# Çalışma satırı ROL adını değil, gerçekten çalışan MODELİ gösterir
# --------------------------------------------------------------------------- #


def test_satirda_rol_adi_degil_model_kimligi_yazar():
    """Rol adı yapılandırmada yazan addır ve yedeğe düşülse bile değişmez."""
    from fusion_cli.cli.repl.work_line import WorkLineSink

    sink = WorkLineSink()

    sink.handle(ModelCallStarted(role="agent", model="nvidia_nim/z-ai/glm-5.2", background=False))

    assert "glm-5.2" in sink.render()
    assert "agent" not in sink.render(), "rol adı kimlik olarak kullanılmamalı"


def test_yedek_devralirsa_satir_gercek_modele_guncellenir():
    """Regresyon: yedek cevap verdiğinde ekran SEÇİLEN modeli göstermeye devam ediyordu.

    Kullanıcı bir kademe seçip başka bir modelin cevabını alıyor ve bunu hiçbir
    yerde göremiyordu; hatayı ancak cevabın niteliğinden sezebiliyordu.
    """
    from fusion_cli.cli.repl.work_line import WorkLineSink

    sink = WorkLineSink()
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

    assert "nemotron-3-ultra-550b-a55b" in sink.render()
    assert "glm-5.2" not in sink.render(), "cevabı vermeyen model satırda kalmamalı"


def test_ayni_modelin_baska_saglayicidaki_kopyasi_ayirt_edilir():
    """Yedek çoğu zaman aynı modelin başka sağlayıcıdaki kopyasıdır.

    Yalnızca model adı gösterilseydi yedeğe düşmüş tur birincille aynı görünürdü.
    """
    from fusion_cli.cli.repl.work_line import WorkLineSink

    sink = WorkLineSink()
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

    assert "openrouter" in sink.render()


# --------------------------------------------------------------------------- #
# Geçen süre olay anında DONDURULMAZ, sorulduğu anda hesaplanır
# --------------------------------------------------------------------------- #


class _SahteSaat:
    """Testte zamanı elle ilerletmek için (RULES: zaman enjekte edilir)."""

    def __init__(self) -> None:
        self.t = 100.0

    def monotonic(self) -> float:
        return self.t

    def now(self) -> float:
        return self.t


def test_gecen_sure_olaysiz_akar():
    """Regresyon: süre `ModelCallStarted` anında hesaplanıp metne gömülüyordu.

    Satır yalnız olay geldiğinde yeniden üretildiği için "0ms"de kalıyor ve
    ancak cevap gelince gerçek değere sıçrıyordu; kullanıcı turun ilerlediğini
    göremiyordu. Artık ARADA HİÇ OLAY OLMADAN da süre akar.
    """
    from fusion_cli.cli.repl.work_line import WorkLineSink

    saat = _SahteSaat()
    sink = WorkLineSink(clock=saat)
    sink.handle(ModelCallStarted(role="nemotron", model="nemotron-super", background=False))

    assert "0ms" in sink.render()

    saat.t += 1.0
    bir_saniye = sink.render()
    saat.t += 11.0
    on_iki_saniye = sink.render()

    assert "1.0s" in bir_saniye
    assert "12.0s" in on_iki_saniye
    assert bir_saniye != on_iki_saniye


def test_calisan_cagri_yokken_satir_bostur():
    """Hiç olay gelmediyse satır çizilmemeli — boş bir kutu gösterilmez."""
    from fusion_cli.cli.repl.work_line import WorkLineSink

    assert WorkLineSink().render() == ""
