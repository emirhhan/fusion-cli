"""Tur sonu kanıt görünürlüğü: geçen doğrulama, ölçülemeyen kapı, gerçek fark (30 Ekim deneme).

Ölçüldü (g4): web sayfası yazıldı, tarayıcı kapısı sayfayı GERÇEKTEN açıp denetledi
(`1 sayfa tarayıcıda açılıp denetlendi`), ama geçen kapı hiçbir olay yaymıyordu ve rapor
bloğu (`✓ Doğrulandı ...`) yalnız `final_text`'e ekleniyordu; cevap akıtılmışsa ekrana
hiç ulaşmıyordu. Kullanıcı kapının çalıştığını göremiyordu.
"""

from __future__ import annotations

import io

from rich.console import Console

from fusion_cli.core.events import ChangesDigested, VerificationPassed
from fusion_cli.core.evidence import CriterionEvidence, EvidenceStatus, ToolUse
from fusion_cli.core.execution_plan import VerificationCheckKind
from fusion_cli.core.tools import ToolContext
from fusion_cli.core.verification import VerificationResult
from fusion_cli.engines.agent import loop as agent_loop
from fusion_cli.engines.agent.approval import ApprovalMode, build_policy
from fusion_cli.engines.agent.change_digest import change_digest
from fusion_cli.engines.agent.loop import AgentDeps, run_agent
from fusion_cli.engines.agent.turn_report import build_turn_report, summarize_evidence
from fusion_cli.ui.renderer import ConsoleRenderer

from .fakes import (
    AlwaysApprove,
    RecordingSink,
    ScriptedProvider,
    make_config,
    model_result,
    tool_call,
)


def _write(path: str) -> ToolUse:
    return ToolUse(name="write_file", ok=True, mutating=True, arguments={"path": path})


def _shell(command: str, output: str, *, exit_code: int = 0) -> ToolUse:
    return ToolUse(
        name="run_shell",
        ok=exit_code == 0,
        mutating=True,
        arguments={"command": command},
        output=f"(çıkış kodu {exit_code})\n{output}",
    )


def _tarayici_kaniti(sayfa: int = 2) -> CriterionEvidence:
    return CriterionEvidence(
        criterion_id="tarayici_sayfalari",
        kind=VerificationCheckKind.TOOL,
        status=EvidenceStatus.PASSED,
        summary=f"{sayfa} sayfa tarayıcıda açılıp denetlendi",
    )


# --- Doğrulama özeti ------------------------------------------------------------ #


def test_tarayici_kapisi_gecince_tek_satirlik_kanit_uretilir():
    gate = VerificationResult(ok=True, evidence=(_tarayici_kaniti(2),))
    report = build_turn_report(("web/index.html",), (_write("web/index.html"),), gate)

    ozet = summarize_evidence(report)

    assert ozet.verified == ("tarayıcı (2 sayfa, konsol temiz)",)
    assert ozet.unmeasured == ()


def test_test_komutu_sayilariyla_ozetlenir():
    tool_uses = (
        _write("a.py"),
        _shell("python3 -m pytest tests -v", "collected 4 items\n4 passed in 0.02s"),
    )
    report = build_turn_report(("a.py",), tool_uses, None)

    assert summarize_evidence(report).verified == ("testler 4/4",)


def test_basarisiz_test_sayisi_toplamdan_ayri_gorunur():
    tool_uses = (
        _write("a.py"),
        _shell("pytest", "3 passed, 1 failed in 0.1s", exit_code=1),
    )
    report = build_turn_report(("a.py",), tool_uses, None)

    assert summarize_evidence(report).verified == ()


def test_sayi_okunamayan_komut_adiyla_gorunur():
    tool_uses = (_write("a.py"), _shell("cargo test", "test result: ok."))
    report = build_turn_report(("a.py",), tool_uses, None)

    assert summarize_evidence(report).verified == ("`cargo test`",)


def test_olculemeyen_kapi_nedeniyle_birlikte_bildirilir():
    gate = VerificationResult(
        ok=True,
        warnings=(
            "TARAYICI ÖLÇÜLEMEDİ (not_measured): Playwright kurulu değil; sayfa doğrulanmadı.",
        ),
    )
    report = build_turn_report(("web/index.html",), (_write("web/index.html"),), gate)

    ozet = summarize_evidence(report)

    assert ozet.verified == ()
    assert any("Playwright kurulu değil" in neden for neden in ozet.unmeasured)
    assert not any("TARAYICI ÖLÇÜLEMEDİ" in neden for neden in ozet.unmeasured)


def test_hic_kanit_yoksa_olculmedi_nedeni_yazilir():
    report = build_turn_report(("a.py",), (_write("a.py"),), None)

    ozet = summarize_evidence(report)

    assert ozet.verified == ()
    assert any("doğrulama komutu çalıştırılmadı" in neden for neden in ozet.unmeasured)


def test_degisiklik_yoksa_ozet_bos():
    assert summarize_evidence(build_turn_report((), (), None)).is_empty


def test_son_degisiklik_kabuk_komutuysa_rapor_nedenini_soyler():
    """g3: testten sonra çalıştırılan `python3 -m paket.cli ...` dosya değiştirebilir
    sayıldı; rapor yalnız "komut ÇALIŞTIRILMADI" diyordu, oysa pytest koşmuştu."""
    tool_uses = (
        _write("a.py"),
        _shell("python3 -m pytest tests", "4 passed in 0.1s"),
        _shell("python3 -m gorevler.cli listele", "[ ] 2 test 2"),
    )
    report = build_turn_report(("a.py",), tool_uses, None)

    metin = report.render()

    assert "python3 -m gorevler.cli listele" in metin
    assert "yeniden" in metin


# --- Gerçek fark özeti ---------------------------------------------------------- #


def test_degisen_satirlar_modelin_iddiasindan_degil_farktan_gelir(tmp_path):
    from fusion_cli.core.tools import ToolContext

    dosya = tmp_path / "depo.py"
    dosya.write_text(
        "yeni_id = len(gorevler) + 1\nreturn [g for g in gorevler if g.tamamlandi]\nkalan = 1\n",
        encoding="utf-8",
    )
    baglam = ToolContext(root=tmp_path)
    baglam.changes.record(dosya)
    dosya.write_text(
        "yeni_id = max(g.id for g in gorevler) + 1\n"
        "return [g for g in gorevler if not g.tamamlandi]\nkalan = 1\n",
        encoding="utf-8",
    )

    satirlar = change_digest(baglam)

    assert satirlar[0] == "depo.py (+2 -2)"
    assert "- yeni_id = len(gorevler) + 1" in satirlar[1]
    assert "+ yeni_id = max(g.id for g in gorevler) + 1" in "\n".join(satirlar)
    assert not any("kalan = 1" in satir for satir in satirlar)


def test_yeni_dosya_icin_satir_listelenmez_yalniz_sayi_yazilir(tmp_path):
    from fusion_cli.core.tools import ToolContext

    yeni = tmp_path / "web" / "index.html"
    yeni.parent.mkdir()
    baglam = ToolContext(root=tmp_path)
    baglam.changes.record_created(yeni)
    yeni.write_text("<html>\n<body>\n</body>\n</html>\n", encoding="utf-8")

    assert change_digest(baglam) == ("web/index.html (yeni dosya, 4 satır)",)


def test_sir_dosyasinin_farki_ozete_girmez(tmp_path):
    from fusion_cli.core.tools import ToolContext

    gizli = tmp_path / ".env"
    gizli.write_text("ANAHTAR=eski\n", encoding="utf-8")
    baglam = ToolContext(root=tmp_path)
    baglam.changes.record(gizli)
    gizli.write_text("ANAHTAR=yeni\n", encoding="utf-8")

    assert change_digest(baglam) == ()


def test_ozet_dosya_ve_satir_sayisiyla_sinirlidir(tmp_path):
    from fusion_cli.core.tools import ToolContext

    baglam = ToolContext(root=tmp_path)
    for numara in range(6):
        dosya = tmp_path / f"d{numara}.txt"
        dosya.write_text("\n".join(f"eski {i}" for i in range(30)), encoding="utf-8")
        baglam.changes.record(dosya)
        dosya.write_text("\n".join(f"yeni {i}" for i in range(30)), encoding="utf-8")

    satirlar = change_digest(baglam)

    basliklar = [s for s in satirlar if "(+30 -30)" in s]
    assert len(basliklar) == 4
    assert any("daha" in satir for satir in satirlar)
    assert len(satirlar) < 60


# --- Döngü: akıtılan cevapta kanıt olayı --------------------------------------- #


class _Publisher:
    def __init__(self, sink):
        self._sink = sink

    def publish(self, event):
        self._sink.handle(event)


class _SabitKapi:
    def __init__(self, sonuc: VerificationResult) -> None:
        self._sonuc = sonuc

    async def verify(self) -> VerificationResult:
        return self._sonuc


def _kur(monkeypatch, provider):
    def _build(spec, **kwargs):
        del spec, kwargs
        return provider

    monkeypatch.setattr(agent_loop, "build_provider", _build)


def _deps(tmp_path, sink, kapi):
    return AgentDeps(
        config=make_config(),
        publisher=_Publisher(sink),
        policy=build_policy(ApprovalMode.AUTO, AlwaysApprove()),
        tool_context=ToolContext(root=tmp_path),
        verifier=kapi,
    )


async def test_gecen_tarayici_kapisi_akitilan_cevapta_olay_yayar(monkeypatch, tmp_path):
    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=(tool_call("write_file", path="web/index.html", content="<p>x</p>"),)
                ),
                model_result("`web/index.html` oluşturuldu."),
            ]
        ),
    )
    kapi = _SabitKapi(VerificationResult(ok=True, evidence=(_tarayici_kaniti(2),)))

    sonuc = await run_agent("web sayfası yaz", _deps(tmp_path, sink, kapi))

    assert sonuc.ok
    gecen = [e for e in sink.events if isinstance(e, VerificationPassed)]
    assert len(gecen) == 1
    assert gecen[0].checks == ("tarayıcı (2 sayfa, konsol temiz)",)
    assert gecen[0].unmeasured == ()
    fark = [e for e in sink.events if isinstance(e, ChangesDigested)]
    assert len(fark) == 1
    assert fark[0].lines == ("web/index.html (yeni dosya, 1 satır)",)


async def test_olculemeyen_kapi_akitilan_cevapta_neden_yayar(monkeypatch, tmp_path):
    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=(tool_call("write_file", path="web/index.html", content="<p>x</p>"),)
                ),
                model_result("`web/index.html` oluşturuldu."),
            ]
        ),
    )
    kapi = _SabitKapi(
        VerificationResult(
            ok=True, warnings=("TARAYICI ÖLÇÜLEMEDİ (not_measured): Playwright kurulu değil.",)
        )
    )

    sonuc = await run_agent("web sayfası yaz", _deps(tmp_path, sink, kapi))

    assert sonuc.ok
    olay = next(e for e in sink.events if isinstance(e, VerificationPassed))
    assert olay.checks == ()
    assert olay.unmeasured == ("Playwright kurulu değil.",)


async def test_oz_denetim_yapilamasa_da_kapi_yesilse_tur_basarili_kalir(monkeypatch, tmp_path):
    """Plan maddesi 2: öz-denetimin çalışamaması tek başına "kısmi" yapmaz (g4: ✓ Görev
    tamamlandı). g3'ün "kısmi"si öz-denetimden değil kanıt tazeliğinden gelmişti."""
    sink = RecordingSink()
    _kur(
        monkeypatch,
        ScriptedProvider(
            [
                model_result(
                    tool_calls=(tool_call("write_file", path="web/index.html", content="<p>x</p>"),)
                ),
                model_result("`web/index.html` oluşturuldu."),
            ]
        ),
    )
    monkeypatch.setattr(agent_loop.review, "review_turn", _denetim_yapilamadi)
    kapi = _SabitKapi(VerificationResult(ok=True, evidence=(_tarayici_kaniti(1),)))
    deps = _deps(tmp_path, sink, kapi)
    deps.config = _oz_denetimli(deps.config)

    sonuc = await run_agent("web sayfası yaz", deps)

    from fusion_cli.core.events import SelfReviewFinished

    bitis = next(e for e in sink.events if isinstance(e, SelfReviewFinished))
    assert bitis.completed is False
    assert sonuc.ok is True


async def _denetim_yapilamadi(*args, **kwargs):
    del args, kwargs
    return None


def _oz_denetimli(config):
    from dataclasses import replace

    return replace(config, runtime=replace(config.runtime, self_review=True))


# --- Ekran satırı --------------------------------------------------------------- #


def _ekran():
    buffer = io.StringIO()
    console = Console(file=buffer, width=100, force_terminal=False, color_system=None)
    return ConsoleRenderer(console), buffer


def test_ekranda_dogrulandi_satiri_basilir():
    renderer, buffer = _ekran()

    renderer.handle(VerificationPassed(checks=("tarayıcı (2 sayfa, konsol temiz)", "testler 4/4")))

    assert "✓ doğrulandı: tarayıcı (2 sayfa, konsol temiz) · testler 4/4" in buffer.getvalue()


def test_ekranda_olculmedi_satiri_nedenle_basilir():
    renderer, buffer = _ekran()

    renderer.handle(VerificationPassed(checks=(), unmeasured=("Playwright kurulu değil.",)))

    cikti = buffer.getvalue()
    assert "ölçülmedi: Playwright kurulu değil." in cikti
    assert "doğrulandı" not in cikti


def test_ekranda_degisen_satirlar_basilir():
    renderer, buffer = _ekran()

    renderer.handle(ChangesDigested(lines=("depo.py (+1 -1)", "  - a", "  + b")))

    cikti = buffer.getvalue()
    assert "depo.py (+1 -1)" in cikti
    assert "  - a" in cikti
