"""Gözlemlenebilirlik dinleyicileri: maliyet, JSON çıktısı, izleme."""

from __future__ import annotations

import io
import json

from fusion_cli.core.events import (
    CandidatesStarted,
    Channel,
    ModelCallFinished,
    StatusChanged,
    TokenReceived,
    ToolExecuted,
    ToolOutcome,
)
from fusion_cli.core.types import ModelResult, TokenUsage
from fusion_cli.observability.cost import CostTracker
from fusion_cli.observability.json_sink import JsonRenderer
from fusion_cli.observability.tracing import LangfuseTracer, is_configured


def _bitti(role, *, prompt=100, completion=50, cost=0.001, ok=True):
    return ModelCallFinished(
        role=role,
        result=ModelResult(
            name=role,
            model=f"saglayici/{role}",
            text="cevap",
            latency_ms=100,
            ok=ok,
            usage=TokenUsage(prompt_tokens=prompt, completion_tokens=completion, cost_usd=cost),
        ),
    )


# --- Maliyet ----------------------------------------------------------------- #


def test_token_ve_maliyet_toplanir():
    tracker = CostTracker()
    tracker.handle(_bitti("agent", prompt=100, completion=50, cost=0.001))
    tracker.handle(_bitti("hakem", prompt=200, completion=20, cost=0.002))

    total = tracker.total
    assert total.prompt_tokens == 300
    assert total.completion_tokens == 70
    assert total.cost_usd == 0.003
    assert tracker.calls == 2


def test_ayni_rolun_cagrilari_birikir():
    tracker = CostTracker()
    for _ in range(3):
        tracker.handle(_bitti("agent", prompt=10, completion=5, cost=0.001))

    role, calls, usage = tracker.by_role()[0]
    assert role == "agent" and calls == 3
    assert usage.total_tokens == 45


def test_basarisiz_cagri_token_saymaz_ama_kaydedilir():
    tracker = CostTracker()
    tracker.handle(_bitti("agent", ok=False))

    assert tracker.calls == 0
    assert tracker.failed_calls == 1
    assert tracker.total.total_tokens == 0


def test_her_rol_sayima_girer():
    """Eski projede yalnızca streaming turları sayılıyordu; hepsi girmeli."""
    tracker = CostTracker()
    for role in ("aday", "hakem", "sentez", "oz-denetim", "ders", "alt-ajan"):
        tracker.handle(_bitti(role))

    assert {row[0] for row in tracker.by_role()} == {
        "aday",
        "hakem",
        "sentez",
        "oz-denetim",
        "ders",
        "alt-ajan",
    }


def test_ilgisiz_olaylar_yok_sayilir():
    tracker = CostTracker()
    tracker.handle(StatusChanged("bir sey"))
    tracker.handle(TokenReceived(Channel.MAIN, "metin"))

    assert tracker.calls == 0


def test_roller_token_toplamina_gore_sirali():
    tracker = CostTracker()
    tracker.handle(_bitti("kucuk", prompt=10, completion=1))
    tracker.handle(_bitti("buyuk", prompt=1000, completion=500))

    assert [row[0] for row in tracker.by_role()] == ["buyuk", "kucuk"]


def test_sifirlama_tum_sayaclari_temizler():
    tracker = CostTracker()
    tracker.handle(_bitti("agent"))
    tracker.reset()

    assert tracker.calls == 0 and tracker.total.total_tokens == 0


def test_token_kullanimi_toplanabilir():
    birlesim = TokenUsage(10, 5, 0.1) + TokenUsage(20, 10, 0.2)

    assert birlesim.prompt_tokens == 30
    assert birlesim.completion_tokens == 15
    assert round(birlesim.cost_usd, 6) == 0.3


# --- JSON çıktısı ------------------------------------------------------------- #


def test_her_olay_tek_satir_json_olur():
    buffer = io.StringIO()
    renderer = JsonRenderer(buffer)

    renderer.handle(StatusChanged("basliyor"))
    renderer.handle(CandidatesStarted(names=("a", "b")))

    satirlar = buffer.getvalue().strip().splitlines()
    assert len(satirlar) == 2
    assert json.loads(satirlar[0]) == {"event": "StatusChanged", "message": "basliyor"}
    assert json.loads(satirlar[1])["names"] == ["a", "b"]


def test_enum_alanlar_degerine_cevrilir():
    buffer = io.StringIO()

    JsonRenderer(buffer).handle(
        ToolExecuted(name="read_file", args={"path": "a"}, outcome=ToolOutcome.OK, output="x")
    )

    payload = json.loads(buffer.getvalue())
    assert payload["outcome"] == "ok"
    assert payload["args"] == {"path": "a"}


def test_ic_ice_dataclass_serilestirilir():
    buffer = io.StringIO()

    JsonRenderer(buffer).handle(_bitti("agent"))

    payload = json.loads(buffer.getvalue())
    assert payload["result"]["model"] == "saglayici/agent"


def test_turkce_karakterler_bozulmaz():
    buffer = io.StringIO()

    JsonRenderer(buffer).handle(StatusChanged("düşünüyor…"))

    assert "düşünüyor…" in buffer.getvalue()


# --- İzleme ------------------------------------------------------------------- #


def test_anahtar_yoksa_izleme_kapali(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    tracer = LangfuseTracer(task="gorev")

    assert not tracer.enabled
    assert tracer.disabled_reason == "anahtar tanımlı değil"


def test_ornek_anahtar_izlemeyi_acmaz(monkeypatch):
    """`.env.example`'daki 'pk-lf-...' değerleri izlemeyi açmamalı."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-...")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-...")

    assert not is_configured()
    assert not LangfuseTracer(task="gorev").enabled


def test_kapali_izleme_olaylari_sessizce_yutar(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    tracer = LangfuseTracer(task="gorev")

    tracer.handle(_bitti("agent"))
    tracer.flush()  # hata vermemeli


# --- Görünürlük ile muhasebe ayrımı ------------------------------------------ #


def test_arka_plan_cagrilari_da_sayima_girer():
    """Hakem, sentez, öz-denetim ve ders çıkarımı GÖSTERİLMEZ ama SAYILIR.

    Eski projede bu ikisi birbirine karıştığı için maliyet takibi çağrı yollarını
    sessizce atlıyordu.
    """
    tracker = CostTracker()
    tracker.handle(_bitti("agent"))
    tracker.handle(
        ModelCallFinished(
            role="hakem",
            result=_bitti("hakem").result,
            background=True,
        )
    )

    assert tracker.calls == 2
    assert {row[0] for row in tracker.by_role()} == {"agent", "hakem"}


def test_arka_plan_cagrisi_ilerleme_satiri_basmaz():
    import io

    from rich.console import Console

    from fusion_cli.core.events import ModelCallStarted
    from fusion_cli.ui.renderer import ConsoleRenderer

    buffer = io.StringIO()
    renderer = ConsoleRenderer(Console(file=buffer, force_terminal=False, width=200, no_color=True))

    renderer.handle(ModelCallStarted(role="hakem", model="m", background=True))
    renderer.handle(ModelCallFinished(role="hakem", result=_bitti("hakem").result, background=True))

    assert buffer.getvalue() == ""


def test_on_plan_cagrisi_bitince_ozet_basar():
    """Başlangıç satırı hiç basılmaz (gürültü); bitişte süre ve token gösterilir."""
    import io

    from rich.console import Console

    from fusion_cli.ui.renderer import ConsoleRenderer

    buffer = io.StringIO()
    renderer = ConsoleRenderer(Console(file=buffer, force_terminal=False, width=200, no_color=True))

    renderer.handle(_bitti("agent"))

    cikti = buffer.getvalue()
    assert "agent" in cikti and "token" in cikti


# --- Biçimlendirme ------------------------------------------------------------ #


def test_sure_insan_olceginde_bicimlenir():
    from fusion_cli.ui.text import format_duration

    assert format_duration(840) == "840ms"
    assert format_duration(2900) == "2.9s"
    assert format_duration(72_000) == "1m12s"


def test_hata_ozeti_json_govdesini_atar():
    from fusion_cli.ui.text import summarize_error

    ozet = summarize_error('APIError: sunucu hatasi {"detay": "cok uzun"} LiteLLM Retried: 1 times')

    assert ozet == "APIError: sunucu hatasi"


def test_hata_ozeti_tekrarlanan_sinif_adini_teke_indirir():
    from fusion_cli.ui.text import summarize_error

    ham = "RateLimitError: litellm.RateLimitError: RateLimitError: OpenrouterException - x"

    assert summarize_error(ham) == "RateLimitError: OpenrouterException - x"


def test_hata_ozeti_saglayici_aciklamasini_korur():
    """Asıl bilgi atılan JSON gövdesinin içinde; kaybolmamalı."""
    from fusion_cli.ui.text import summarize_error

    ham = (
        "RateLimitError: litellm.RateLimitError: OpenrouterException - "
        '{"error":{"message":"Rate limit exceeded: free-models-per-day","code":429}}'
    )

    ozet = summarize_error(ham)

    assert "Rate limit exceeded" in ozet
    # Sağlayıcı istisna adı kullanıcıya bir şey söylemiyor; atılmalı.
    assert "OpenrouterException" not in ozet


def test_hata_ozeti_cumledeki_noktayi_modul_oneki_sanmaz():
    from fusion_cli.ui.text import summarize_error

    ozet = summarize_error("Timeout: APITimeoutError - Request timed out. Error_str: bitti")

    assert "Request timed out." in ozet


def test_hata_ozeti_ust_sinirda_kirpar():
    from fusion_cli.ui.text import ERROR_SUMMARY_CHARS, summarize_error

    assert len(summarize_error("x" * 500)) <= ERROR_SUMMARY_CHARS
