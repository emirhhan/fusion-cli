"""Kabul koşucusunun saf mantığı: sınıflandırma, özet, ölçüler, ön-kontrol, akış."""

from __future__ import annotations

import asyncio
import io
from contextlib import contextmanager
from pathlib import Path

import pytest
from evals.kabul import preflight, runner
from evals.kabul.areas import load_area
from evals.kabul.areas.site_clone import _site_root
from evals.kabul.areas.site_clone import inspect as inspect_site
from evals.kabul.areas.site_clone_probe import grid_columns, similarity
from evals.kabul.model import Area, Check, Inspection, Outcome, RunMetrics, classify
from evals.kabul.report import summarize


def _gecen() -> Inspection:
    return Inspection(checks=(Check("a", True), Check("b", True)))


def test_classify_tum_maddeler_gecince_gecti() -> None:
    assert classify(_gecen(), RunMetrics(), "") is Outcome.PASSED


def test_classify_dusen_madde_kaldi() -> None:
    denetim = Inspection(checks=(Check("a", True), Check("b", False)))
    assert classify(denetim, RunMetrics(), "") is Outcome.FAILED


def test_classify_surucu_hatasi_ve_bos_denetim_gecersiz() -> None:
    assert classify(_gecen(), RunMetrics(), "eşleşme yok") is Outcome.INVALID
    assert classify(Inspection(), RunMetrics(), "") is Outcome.INVALID
    assert classify(Inspection(invalid_reason="php yok"), RunMetrics(), "") is Outcome.INVALID


def test_classify_web_modeli_karsiladiysa_ogretmen_destekli() -> None:
    assert classify(_gecen(), RunMetrics(web_model_calls=3), "") is Outcome.TEACHER_ASSISTED


def test_metrics_from_surucu_sayaclarini_okur() -> None:
    olcu = runner.metrics_from(
        {
            "sayaclar": {"model_cagrisi": 7, "web_model_cagrisi": 1, "istem_token": 900},
            "araclar": ["read_file", "write_file"],
            "turlar": [{"sure_sn": 12.5}],
        }
    )
    assert (olcu.model_calls, olcu.web_model_calls, olcu.tool_calls) == (7, 1, 2)
    assert (olcu.prompt_tokens, olcu.elapsed_s) == (900, 12.5)


def test_metrics_from_bos_surucu_ciktisinda_sifir() -> None:
    assert runner.metrics_from({"hata": "x"}) == RunMetrics()


def test_grid_columns_yalniz_ilk_satiri_sayar() -> None:
    assert grid_columns([0, 300, 600, 900, 0, 300], [100, 100, 101, 100, 500, 500]) == 4
    assert grid_columns([0, 0, 0], [100, 500, 900]) == 1
    assert grid_columns([], []) == 0


def _png(renk: int) -> bytes:
    from PIL import Image

    tampon = io.BytesIO()
    Image.new("L", (200, 300), color=renk).save(tampon, format="PNG")
    return tampon.getvalue()


def test_similarity_ayni_resimde_bir_zit_resimde_sifir() -> None:
    assert similarity(_png(120), _png(120)) == 1.0
    assert similarity(_png(0), _png(255)) == 0.0


def test_site_root_alt_klasordeki_wordpressi_bulur(tmp_path: Path) -> None:
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "wp-config.php").write_text("<?php", encoding="utf-8")
    assert _site_root(tmp_path) == tmp_path / "site"


def test_site_inspect_wordpress_yoksa_madde_duser_gecersiz_degil(tmp_path: Path) -> None:
    denetim = inspect_site(tmp_path, {})
    if denetim.invalid_reason:
        pytest.skip("wp-cli ya da php yok")
    assert denetim.checks and not denetim.all_passed


def test_preflight_eksik_arac_modeli_sormadan_durur(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    alan = Area(
        "x", "g", 1, lambda _w, _v: Inspection(), required_executables=("yok-boyle-bir-arac",)
    )
    monkeypatch.setattr(preflight, "_model_probe", lambda _c: pytest.fail("model sorulmamalı"))
    rapor = preflight.run_preflight([alan], tmp_path, None)
    assert not rapor.passed and "yok-boyle-bir-arac" in rapor.failures()


def test_preflight_disk_esigi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(preflight, "MIN_FREE_DISK_GB", 10**9)
    assert not preflight._disk(tmp_path).passed


def test_run_job_hazirlik_gorev_ve_denetimi_baglar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gorulen: dict[str, object] = {}

    @contextmanager
    def hazirla(workdir: Path):  # type: ignore[no-untyped-def]  # test içi kısa fikstür
        (workdir / "kopya").mkdir()
        yield {"repo": str(workdir / "kopya"), "url": "http://yerel"}

    def denetle(workdir: Path, degerler: object) -> Inspection:
        gorulen["degerler"] = degerler
        return _gecen()

    async def sahte_surucu(
        job: object, kok: Path, gorev: str, options: object
    ) -> dict[str, object]:
        gorulen["kok"], gorulen["gorev"] = kok, gorev
        return {"turlar": [{"ok": True, "metin": "bitti", "sure_sn": 3}], "sayaclar": {}}

    monkeypatch.setattr(runner, "_drive", sahte_surucu)
    alan = Area("deneme", "{url} adresinde çalış", 10, denetle, prepare=hazirla, root_key="repo")
    job = runner.Job(alan, 1, tmp_path / "is")
    kayit = asyncio.run(runner.run_job(job, runner.RunnerOptions(1, 0, None), asyncio.Lock()))
    assert gorulen["kok"] == tmp_path / "is" / "kopya"
    assert gorulen["gorev"] == "http://yerel adresinde çalış"
    assert gorulen["degerler"]["agent_text"] == "bitti"  # type: ignore[index]
    assert kayit.outcome is Outcome.PASSED and kayit.agent_ok is True


def test_run_job_cokmus_denetci_kosuyu_gecersiz_yapar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def coken(workdir: Path, degerler: object) -> Inspection:
        raise ValueError("bozuk")

    async def sahte_surucu(*_args: object) -> dict[str, object]:
        return {"turlar": [{"ok": True, "metin": ""}]}

    monkeypatch.setattr(runner, "_drive", sahte_surucu)
    job = runner.Job(Area("d", "g", 1, coken), 1, tmp_path / "is")
    kayit = asyncio.run(runner.run_job(job, runner.RunnerOptions(1, 0, None), asyncio.Lock()))
    assert kayit.outcome is Outcome.INVALID and "bozuk" in kayit.inspection.invalid_reason


def test_summarize_gecersizi_orana_katmaz_sahte_basariyi_sayar() -> None:
    def kayit(sonuc: Outcome, ok: bool) -> runner.RunRecord:
        denetim = _gecen() if sonuc is Outcome.PASSED else Inspection(checks=(Check("a", False),))
        return runner.RunRecord("alan", 1, "", sonuc, denetim, RunMetrics(), agent_ok=ok)

    ozet = summarize(
        [kayit(Outcome.PASSED, True), kayit(Outcome.FAILED, True), kayit(Outcome.INVALID, False)]
    )[0]
    assert (ozet.measured, ozet.passed, ozet.false_success) == (2, 1, 1)


def test_kayit_defterindeki_her_alan_yuklenir() -> None:
    for ad in ("site_kopyasi", "kendini_gelistirme", "tarayici"):
        assert load_area(ad).name == ad
    with pytest.raises(KeyError):
        load_area("yok")


def test_magaza_varsayilan_gorunumde_kaldiysa_yakalanir():
    from evals.kabul.areas.site_clone_probe import default_style_markers, shrunken_slides

    varsayilan = {
        "baslik": "rgb(0, 0, 238)",
        "fiyat": "rgb(149, 142, 9)",
        "dugme": "rgb(127, 84, 179)",
    }
    uyarlanmis = {
        "baslik": "rgba(0, 0, 0, 0.87)",
        "fiyat": "rgb(23, 22, 32)",
        "dugme": "rgb(0, 0, 0)",
    }

    assert len(default_style_markers(varsayilan)) == 3
    assert default_style_markers(uyarlanmis) == []
    assert default_style_markers({}) == []
    assert shrunken_slides([0.25, 0.25, 1.0]) == 2
    assert shrunken_slides([1.0, 0.8]) == 0
    assert shrunken_slides([]) == 0


def test_kaynak_da_tasiyorsa_kopyanin_ayni_tasmasi_kusur_sayilmaz():
    """dalga45/46: sneaksup.com 1440 px'te kendisi 365 px taşıyor; birebir kopya kalıyordu."""
    from evals.kabul.areas.site_clone_probe import overflow_check

    assert overflow_check(365, 365).passed
    assert overflow_check(0, None).passed
    assert not overflow_check(365, 0).passed
    assert not overflow_check(365, None).passed
    assert "kaynak 365 px" in overflow_check(365, 365).detail
