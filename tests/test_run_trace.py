"""Koşu izi: bir turun neden düştüğü transkript okumadan söylenebilmeli.

Ölçüldü (5 Eylül canlı koşusu): 24 görevlik setteki beş başarısızlığın sebebini
bulmak için `_transkript.jsonl` dosyaları elle okundu. Bu ölçeklenmez; kayıp
sınıfı olayların KENDİSİNDEN çıkarılabilir olmalı.
"""

from __future__ import annotations

from fusion_cli.core.events import (
    ExecutionPaused,
    ExecutionStepStarted,
    ExecutionStepVerified,
    ModelCallFinished,
    ToolCallRepaired,
    ToolExecuted,
    ToolOutcome,
)
from fusion_cli.core.trace import FailureKind, summarize_run
from fusion_cli.core.types import ModelResult


def _model(text: str = "tamam", error: str | None = None) -> ModelCallFinished:
    return ModelCallFinished(
        role="secilen",
        result=ModelResult(
            name="secilen",
            model="test/model",
            text=text,
            latency_ms=10,
            ok=error is None,
            error=error,
        ),
    )


def _tool(name: str, outcome: ToolOutcome, output: str = "") -> ToolExecuted:
    return ToolExecuted(name=name, args={}, outcome=outcome, output=output)


def test_arac_kapsam_engeli_ayri_bir_kayip_sinifi():
    ozet = summarize_run(
        [
            _tool("read_file", ToolOutcome.BLOCKED, "izin verilen kapsamında değil"),
            _tool("run_shell", ToolOutcome.OK),
        ]
    )

    assert FailureKind.TOOL_SCOPE in ozet.failures
    assert ozet.tool_calls == 2
    assert ozet.blocked_tools == 1


def test_bos_yanit_ve_ayristirma_kurtarmasi_sayilir():
    ozet = summarize_run([_model(text=""), ToolCallRepaired(), _model()])

    assert FailureKind.EMPTY_RESPONSE in ozet.failures
    assert ozet.parse_repairs == 1
    assert ozet.model_calls == 2


def test_saglayici_hatasi_dogrulama_hatasindan_ayrilir():
    ozet = summarize_run(
        [
            _model(error="rate limit"),
            ExecutionStepVerified(
                plan_id="p", step_id="s", ok=False, evidence=(), findings=("test düştü",)
            ),
        ]
    )

    assert FailureKind.PROVIDER in ozet.failures
    assert FailureKind.VERIFICATION in ozet.failures


def test_butce_ve_duraklama_sebebi_ozete_gecer():
    ozet = summarize_run(
        [
            ExecutionStepStarted(plan_id="p", step_id="s", index=1, total_steps=2, goal="yaz"),
            ExecutionPaused(plan_id="p", reason="Workflow bütçesi tükendi; duraklatıldı."),
        ]
    )

    assert FailureKind.BUDGET in ozet.failures
    assert ozet.steps == 1
    assert "bütçesi tükendi" in ozet.pause_reason


def test_temiz_kosu_hicbir_kayip_sinifi_uretmez():
    ozet = summarize_run([_model(), _tool("write_file", ToolOutcome.OK)])

    assert ozet.failures == ()
    assert ozet.ok


def test_ozet_tek_satirlik_teshis_uretir():
    ozet = summarize_run([_tool("read_file", ToolOutcome.BLOCKED, "izin verilen kapsamında değil")])

    satir = ozet.headline()
    assert "araç kapsamı" in satir.casefold()


# --- Diske yazılan iz ve okuma yolu ------------------------------------------- #


def test_iz_diske_jsonl_olarak_yazilir_ve_geri_okunur(tmp_path):
    """Koşu bittikten SONRA teşhis edilebilmeli: iz kalıcı olmalı."""
    from fusion_cli.observability.trace_store import TraceStore

    store = TraceStore(tmp_path)
    yazici = store.writer("kosu-1")
    yazici.handle(_tool("read_file", ToolOutcome.BLOCKED, "izin verilen kapsamında değil"))
    yazici.handle(_model())
    yazici.close()

    ozet = summarize_run(store.read("kosu-1"))

    assert FailureKind.TOOL_SCOPE in ozet.failures
    assert ozet.model_calls == 1


def test_izde_sir_maskelenir(tmp_path):
    from fusion_cli.observability.trace_store import TraceStore

    store = TraceStore(tmp_path)
    yazici = store.writer("kosu-2")
    yazici.handle(_tool("run_shell", ToolOutcome.OK, "api_key=sk-gercek-anahtar"))
    yazici.close()

    ham = (tmp_path / "kosu-2.jsonl").read_text(encoding="utf-8")

    assert "sk-gercek-anahtar" not in ham


def test_son_kosu_bulunur(tmp_path):
    from fusion_cli.observability.trace_store import TraceStore

    store = TraceStore(tmp_path)
    for ad in ("eski", "yeni"):
        yazici = store.writer(ad)
        yazici.handle(_model())
        yazici.close()

    assert store.latest() == "yeni"
    assert set(store.runs()) == {"eski", "yeni"}


def test_gozlemciler_kosuyu_ize_yazar(tmp_path):
    """Her tur, teşhis edilebilmesi için kendi izini bırakmalı."""
    from fusion_cli.cli.session import build_observers

    gozlemciler = build_observers("görev", trace_dir=tmp_path)
    for sink in gozlemciler.sinks:
        sink.handle(_tool("read_file", ToolOutcome.BLOCKED, "izin verilen kapsamında değil"))
    gozlemciler.finish()

    from fusion_cli.observability.trace_store import TraceStore

    store = TraceStore(tmp_path)
    son = store.latest()
    assert son is not None
    ozet = summarize_run(store.read(son))
    assert FailureKind.TOOL_SCOPE in ozet.failures


def test_iz_dizini_verilmezse_gozlemciler_calismaya_devam_eder():
    from fusion_cli.cli.session import build_observers

    gozlemciler = build_observers("görev")
    gozlemciler.finish()

    assert gozlemciler.sinks


# --- `fusion trace` komutu ----------------------------------------------------- #


def test_trace_komutu_son_kosunun_teshisini_basar(tmp_path, capsys):
    from fusion_cli.cli.trace_command import render_trace
    from fusion_cli.observability.trace_store import TraceStore

    store = TraceStore(tmp_path)
    yazici = store.writer("kosu")
    yazici.handle(_tool("read_file", ToolOutcome.BLOCKED, "izin verilen kapsamında değil"))
    yazici.handle(_model())
    yazici.close()

    render_trace(store, run_id=None)

    cikti = capsys.readouterr().out
    assert "araç kapsamı" in cikti.casefold()
    assert "kosu" in cikti


def test_trace_komutu_kayit_yoksa_aciklama_verir(tmp_path, capsys):
    from fusion_cli.cli.trace_command import render_trace
    from fusion_cli.observability.trace_store import TraceStore

    render_trace(TraceStore(tmp_path), run_id=None)

    assert "koşu kaydı" in capsys.readouterr().out.casefold()
