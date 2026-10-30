"""Kendini geliştirme döngüsü, 2. halka: eklemeli aday → ölç → ayrı kümede doğrula → öner.

Gerçek model çağrısı YOKTUR: sağlayıcı ve değerlendirici sahtedir. İstem dosyasının
önerinin kendisiyle DEĞİŞMEDİĞİ, yalnız `uygula` ile değiştiği ayrıca doğrulanır.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
from evals.dongu_kaydi import kayitlari_oku
from evals.metrics import RunReport, TaskResult
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion
from prompt_opt.additive import AdditiveGenerator, FailureNote, addition_of
from prompt_opt.apply import apply_proposal, rollback_prompt
from prompt_opt.campaign import (
    OUTCOME_HELDOUT_REGRESSION,
    OUTCOME_NO_CANDIDATE,
    OUTCOME_NO_GAIN,
    OUTCOME_PROPOSED,
    OverfitError,
    RoundSetup,
    check_heldout,
    run_round,
)
from prompt_opt.evaluator import PromptOverrideRunner, SuiteEvaluator
from prompt_opt.model_provider import ModelSnippetProvider, build_request, parse_snippets
from prompt_opt.proposals import STATUS_APPLIED, STATUS_ROLLED_BACK, ProposalStore
from prompt_opt.targets import TARGETS, PromptTarget, get_target, override
from prompt_opt.versioning import PromptStore

from fusion_cli.core.errors import EvalError
from fusion_cli.core.types import ModelResult

TEMEL = "Kurallar:\n1. Önce oku.\n2. Sonra yaz.\n3. Her zaman test çalıştır ve sonucu bildir.\n" * 3


def _gorev(kimlik: str, istek: str | None = None) -> EvalTask:
    return EvalTask(
        id=kimlik,
        request=istek or f"{kimlik} için dosyayı düzelt",
        criterion=SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="tamam"),
    )


def _kume(*kimlikler: str, onek: str = "") -> tuple[EvalTask, ...]:
    return tuple(_gorev(f"{onek}{kimlik}") for kimlik in kimlikler)


def _rapor(basari: dict[str, bool]) -> RunReport:
    return RunReport(
        results=tuple(
            TaskResult(
                task_id=kimlik,
                success=ok,
                first_attempt_success=ok,
                retries=0,
                model_calls=1,
                duration_seconds=1.0,
            )
            for kimlik, ok in basari.items()
        )
    )


class _SahteDegerlendirici:
    """Metin → başarı haritası; çağrı sayısını tutar."""

    def __init__(self, skorlar: dict[str, dict[str, bool]]) -> None:
        self._skorlar = skorlar
        self.cagrilar: list[str] = []

    async def evaluate(self, prompt_text: str) -> RunReport:
        self.cagrilar.append(prompt_text)
        return _rapor(self._skorlar[prompt_text])


class _SahteSaglayici:
    def __init__(self, ekler: tuple[str, ...]) -> None:
        self._ekler = ekler
        self.gorulen_basarisizlar: tuple[FailureNote, ...] = ()
        self.cagri = 0

    async def propose(self, base_text, failures, count):
        self.cagri += 1
        self.gorulen_basarisizlar = tuple(failures)
        return self._ekler[:count]


# --------------------------------------------------------------------------- #
# Eklemeli üretim
# --------------------------------------------------------------------------- #


async def test_aday_temeli_birebir_korur_ve_yalniz_ek_ekler():
    uretici = AdditiveGenerator(_SahteSaglayici(("Değişiklikten sonra testi yeniden çalıştır.",)))
    (aday,) = await uretici.generate(TEMEL, 3)
    assert aday.startswith(TEMEL)
    assert addition_of(TEMEL, aday) == "Değişiklikten sonra testi yeniden çalıştır."


async def test_tam_yeniden_yazim_ve_asiri_uzun_ek_reddedilir():
    yeniden_yazim = "Tamamen yeni bir istem. " * 50
    uretici = AdditiveGenerator(_SahteSaglayici((yeniden_yazim, "kısa ek madde burada")))
    adaylar = await uretici.generate(TEMEL, 3)
    assert [addition_of(TEMEL, aday) for aday in adaylar] == ["kısa ek madde burada"]


async def test_temelde_zaten_olan_tekrarli_ve_bos_ekler_elenir():
    uretici = AdditiveGenerator(
        _SahteSaglayici(
            ("Önce oku.", "  ", "yeni madde", "yeni madde", "```\nkod bloğu madde\n```")
        )
    )
    adaylar = await uretici.generate(TEMEL, 5)
    assert [addition_of(TEMEL, aday) for aday in adaylar] == ["yeni madde", "kod bloğu madde"]


async def test_aday_sayisi_sinirlanir():
    uretici = AdditiveGenerator(_SahteSaglayici(("a madde", "b madde", "c madde")))
    assert len(await uretici.generate(TEMEL, 2)) == 2


async def test_basarisiz_gorevler_saglayiciya_ipucu_olarak_gider():
    saglayici = _SahteSaglayici(("yeni madde",))
    notlar = (FailureNote("g1", "bir şey yap"),)
    await AdditiveGenerator(saglayici, failures=notlar).generate(TEMEL, 1)
    assert saglayici.gorulen_basarisizlar == notlar


# --------------------------------------------------------------------------- #
# Aşırı uyum koruması
# --------------------------------------------------------------------------- #


def test_ayni_kume_asiri_uyum_diye_reddedilir():
    kume = _kume("a", "b", "c")
    with pytest.raises(OverfitError, match="aynı görevleri"):
        check_heldout(kume, kume, min_tasks=3)


def test_kismen_ortak_gorev_de_reddedilir():
    with pytest.raises(OverfitError):
        check_heldout(_kume("a", "b", "c"), _kume("c", "d", "e"), min_tasks=3)


def test_ayni_istek_farkli_kimlikle_de_ortak_sayilir():
    optimizasyon = (_gorev("a", "Aynı İSTEK"), _gorev("b"), _gorev("c"))
    ayri = (_gorev("x", "aynı   istek"), _gorev("y"), _gorev("z"))
    with pytest.raises(OverfitError):
        check_heldout(optimizasyon, ayri, min_tasks=3)


def test_cok_kucuk_kume_reddedilir():
    with pytest.raises(OverfitError, match="en az 3"):
        check_heldout(_kume("a", "b", "c"), _kume("x"), min_tasks=3)


def test_ayri_kumeler_kabul_edilir():
    check_heldout(_kume("a", "b", "c"), _kume("x", "y", "z"), min_tasks=3)


# --------------------------------------------------------------------------- #
# Öneri turu
# --------------------------------------------------------------------------- #


def _kurulum(tmp_path: Path, **degisiklik) -> RoundSetup:
    degerler = {
        "prompt": "system",
        "base_text": TEMEL,
        "suite": "hata",
        "heldout_suite": "ayri",
        "opt_tasks": _kume("a", "b", "c", "d"),
        "heldout_tasks": _kume("x", "y", "z"),
        "log_path": tmp_path / "kayit.jsonl",
        "now": lambda: 1_800_000_000.0,
        "timestamp": lambda zaman: f"t{int(zaman)}",
    }
    degerler.update(degisiklik)
    return RoundSetup(**degerler)


def _aday(ek: str = "Her değişiklikten sonra testi çalıştır.") -> str:
    return f"{TEMEL}\n{ek}\n"


async def test_iyilesen_ve_ayri_kumede_gerilemeyen_aday_oneri_olur(tmp_path):
    aday = _aday()
    opt = _SahteDegerlendirici(
        {
            TEMEL: {"a": True, "b": False, "c": False, "d": False},
            aday: {"a": True, "b": True, "c": True, "d": False},
        }
    )
    ayri = _SahteDegerlendirici(
        {
            TEMEL: {"x": True, "y": False, "z": False},
            aday: {"x": True, "y": True, "z": False},
        }
    )
    depo = ProposalStore(tmp_path / "oneriler")
    sonuc = await run_round(
        _kurulum(tmp_path),
        provider=_SahteSaglayici(("Her değişiklikten sonra testi çalıştır.",)),
        opt_evaluator=opt,
        heldout_evaluator=ayri,
        store=depo,
    )
    assert sonuc.outcome == OUTCOME_PROPOSED
    assert (sonuc.opt_base, sonuc.opt_candidate) == (0.25, 0.75)
    assert sonuc.proposal is not None
    kayitli = depo.get(sonuc.proposal.id)
    assert kayitli.candidate_text == aday
    assert kayitli.addition == "Her değişiklikten sonra testi çalıştır."
    assert (kayitli.heldout_base, kayitli.heldout_candidate) == (
        pytest.approx(1 / 3),
        pytest.approx(2 / 3),
    )
    satir = kayitlari_oku(tmp_path / "kayit.jsonl")[-1]
    assert satir["olay"] == "oneri"
    assert satir["sonuc"] == OUTCOME_PROPOSED
    assert satir["opt_skoru"] == 0.75
    assert satir["heldout_skoru"] == pytest.approx(2 / 3)


async def test_ayri_kumede_gerileyen_aday_oneri_olmaz(tmp_path):
    aday = _aday()
    opt = _SahteDegerlendirici(
        {
            TEMEL: {"a": True, "b": False, "c": False, "d": False},
            aday: {"a": True, "b": True, "c": True, "d": True},
        }
    )
    ayri = _SahteDegerlendirici(
        {
            TEMEL: {"x": True, "y": True, "z": False},
            aday: {"x": False, "y": True, "z": True},  # x bozuldu: aşırı uyum işareti
        }
    )
    depo = ProposalStore(tmp_path / "oneriler")
    sonuc = await run_round(
        _kurulum(tmp_path),
        provider=_SahteSaglayici(("Her değişiklikten sonra testi çalıştır.",)),
        opt_evaluator=opt,
        heldout_evaluator=ayri,
        store=depo,
    )
    assert sonuc.outcome == OUTCOME_HELDOUT_REGRESSION
    assert "x" in sonuc.detail
    assert sonuc.proposal is None
    assert depo.list() == ()
    assert kayitlari_oku(tmp_path / "kayit.jsonl")[-1]["sonuc"] == OUTCOME_HELDOUT_REGRESSION


async def test_ayni_kume_hicbir_model_cagrisi_yapmadan_reddedilir(tmp_path):
    kume = _kume("a", "b", "c")
    opt = _SahteDegerlendirici({})
    saglayici = _SahteSaglayici(("x",))
    with pytest.raises(OverfitError):
        await run_round(
            _kurulum(tmp_path, opt_tasks=kume, heldout_tasks=kume),
            provider=saglayici,
            opt_evaluator=opt,
            heldout_evaluator=opt,
            store=ProposalStore(tmp_path / "o"),
        )
    assert opt.cagrilar == []
    assert saglayici.cagri == 0


async def test_temel_zaten_hepsini_geciyorsa_aday_uretilmez(tmp_path):
    opt = _SahteDegerlendirici({TEMEL: {"a": True, "b": True, "c": True, "d": True}})
    saglayici = _SahteSaglayici(("x madde",))
    sonuc = await run_round(
        _kurulum(tmp_path),
        provider=saglayici,
        opt_evaluator=opt,
        heldout_evaluator=opt,
        store=ProposalStore(tmp_path / "o"),
    )
    assert sonuc.outcome == OUTCOME_NO_GAIN
    assert saglayici.cagri == 0


async def test_optimizasyon_kumesinde_iyilesme_yoksa_ayri_kume_olculmez(tmp_path):
    aday = _aday()
    opt = _SahteDegerlendirici(
        {
            TEMEL: {"a": True, "b": False, "c": False, "d": False},
            aday: {"a": True, "b": False, "c": False, "d": False},
        }
    )
    ayri = _SahteDegerlendirici({})
    sonuc = await run_round(
        _kurulum(tmp_path),
        provider=_SahteSaglayici(("Her değişiklikten sonra testi çalıştır.",)),
        opt_evaluator=opt,
        heldout_evaluator=ayri,
        store=ProposalStore(tmp_path / "o"),
    )
    assert sonuc.outcome == OUTCOME_NO_CANDIDATE
    assert ayri.cagrilar == []


async def test_baslangic_degerlendirmesi_tekrarlanmaz(tmp_path):
    aday = _aday()
    opt = _SahteDegerlendirici(
        {
            TEMEL: {"a": True, "b": False, "c": False, "d": False},
            aday: {"a": True, "b": True, "c": True, "d": True},
        }
    )
    ayri = _SahteDegerlendirici(
        {TEMEL: {"x": True, "y": True, "z": True}, aday: {"x": True, "y": True, "z": True}}
    )
    await run_round(
        _kurulum(tmp_path),
        provider=_SahteSaglayici(("Her değişiklikten sonra testi çalıştır.",)),
        opt_evaluator=opt,
        heldout_evaluator=ayri,
        store=ProposalStore(tmp_path / "o"),
    )
    assert opt.cagrilar.count(TEMEL) == 1  # temel bir kez ölçüldü


# --------------------------------------------------------------------------- #
# Uygula / geri al
# --------------------------------------------------------------------------- #


def _oneri_hazirla(tmp_path: Path):
    """Geçici istem dosyası + bekleyen bir öneri döndür."""
    dosya = tmp_path / "system.md"
    dosya.write_text(TEMEL, encoding="utf-8")
    hedef = PromptTarget("system", dosya, "yok.modul", "X")
    import asyncio

    aday = _aday()
    opt = _SahteDegerlendirici(
        {
            TEMEL: {"a": True, "b": False, "c": False, "d": False},
            aday: {"a": True, "b": True, "c": True, "d": True},
        }
    )
    ayri = _SahteDegerlendirici(
        {TEMEL: {"x": True, "y": True, "z": True}, aday: {"x": True, "y": True, "z": True}}
    )
    depo = ProposalStore(tmp_path / "oneriler")
    sonuc = asyncio.run(
        run_round(
            _kurulum(tmp_path),
            provider=_SahteSaglayici(("Her değişiklikten sonra testi çalıştır.",)),
            opt_evaluator=opt,
            heldout_evaluator=ayri,
            store=depo,
        )
    )
    assert sonuc.proposal is not None
    return hedef, depo, sonuc.proposal


def test_oneri_istem_dosyasini_degistirmez(tmp_path):
    hedef, _, _ = _oneri_hazirla(tmp_path)
    assert hedef.read() == TEMEL


def test_uygula_dosyayi_yazar_ve_orijinali_surum_olarak_saklar(tmp_path):
    hedef, depo, oneri = _oneri_hazirla(tmp_path)
    surumler = PromptStore(tmp_path / "surumler")
    degisim = apply_proposal(
        oneri.id,
        proposals=depo,
        versions=surumler,
        log_path=tmp_path / "kayit.jsonl",
        now=lambda: 1.0,
        resolve_target=lambda _: hedef,
    )
    assert hedef.read() == oneri.candidate_text
    assert [v.text for v in surumler.history("system")] == [TEMEL, oneri.candidate_text]
    assert degisim.version == 2
    guncel = depo.get(oneri.id)
    assert (guncel.status, guncel.applied_version) == (STATUS_APPLIED, 2)
    assert kayitlari_oku(tmp_path / "kayit.jsonl")[-1]["olay"] == "oneri_uygulandi"


def test_geri_al_orijinal_metni_dosyaya_dondurur(tmp_path):
    hedef, depo, oneri = _oneri_hazirla(tmp_path)
    surumler = PromptStore(tmp_path / "surumler")
    ortak = {
        "proposals": depo,
        "versions": surumler,
        "log_path": tmp_path / "k.jsonl",
        "now": lambda: 1.0,
    }
    apply_proposal(oneri.id, resolve_target=lambda _: hedef, **ortak)
    degisim = rollback_prompt("system", resolve_target=lambda _: hedef, **ortak)
    assert hedef.read() == TEMEL
    assert degisim.version == 3  # geri alma geçmişi silmez, yeni sürüm olarak yayımlanır
    assert depo.get(oneri.id).status == STATUS_ROLLED_BACK


def test_bayat_oneri_uygulanmaz(tmp_path):
    hedef, depo, oneri = _oneri_hazirla(tmp_path)
    hedef.write(TEMEL + "\nelle eklenen satır\n")
    with pytest.raises(EvalError, match="bayat"):
        apply_proposal(
            oneri.id,
            proposals=depo,
            versions=PromptStore(tmp_path / "s"),
            log_path=tmp_path / "k.jsonl",
            now=lambda: 1.0,
            resolve_target=lambda _: hedef,
        )
    assert "elle eklenen satır" in hedef.read()


def test_uygulanmis_oneri_ikinci_kez_uygulanmaz(tmp_path):
    hedef, depo, oneri = _oneri_hazirla(tmp_path)
    ortak = {
        "proposals": depo,
        "versions": PromptStore(tmp_path / "s"),
        "log_path": tmp_path / "k",
        "now": lambda: 1.0,
    }
    apply_proposal(oneri.id, resolve_target=lambda _: hedef, **ortak)
    with pytest.raises(EvalError, match="yalnız bekleyen"):
        apply_proposal(oneri.id, resolve_target=lambda _: hedef, **ortak)


def test_elle_duzenlenmis_dosya_geri_almada_ezilmez(tmp_path):
    hedef, depo, oneri = _oneri_hazirla(tmp_path)
    ortak = {
        "proposals": depo,
        "versions": PromptStore(tmp_path / "s"),
        "log_path": tmp_path / "k",
        "now": lambda: 1.0,
    }
    apply_proposal(oneri.id, resolve_target=lambda _: hedef, **ortak)
    hedef.write(hedef.read() + "kullanıcı notu\n")
    with pytest.raises(EvalError, match="elle düzenlenmiş"):
        rollback_prompt("system", resolve_target=lambda _: hedef, **ortak)
    assert "kullanıcı notu" in hedef.read()


def test_dosya_yazimi_dusunce_depo_geri_alinir(tmp_path):
    hedef, depo, oneri = _oneri_hazirla(tmp_path)

    class _YazilamayanHedef(PromptTarget):
        def write(self, text: str) -> None:
            raise OSError("disk dolu")

    bozuk = _YazilamayanHedef("system", hedef.file, "yok.modul", "X")
    surumler = PromptStore(tmp_path / "s")
    with pytest.raises(EvalError, match="geri alındı"):
        apply_proposal(
            oneri.id,
            proposals=depo,
            versions=surumler,
            log_path=tmp_path / "k",
            now=lambda: 1.0,
            resolve_target=lambda _: bozuk,
        )
    assert surumler.current("system").text == TEMEL  # depo ile dosya ayrışmadı
    assert depo.get(oneri.id).status == "bekliyor"


def test_surum_numarasi_ile_geri_alma_ve_gecmis_yoksa_hata(tmp_path):
    hedef, depo, _ = _oneri_hazirla(tmp_path)
    ortak = {
        "proposals": depo,
        "versions": PromptStore(tmp_path / "s"),
        "log_path": tmp_path / "k",
        "now": lambda: 1.0,
    }
    with pytest.raises(EvalError, match="sürüm geçmişi yok"):
        rollback_prompt("system", resolve_target=lambda _: hedef, **ortak)


# --------------------------------------------------------------------------- #
# Hedefler, değerlendirici ve model sağlayıcısı
# --------------------------------------------------------------------------- #


def test_izin_listesindeki_her_istem_dosyasi_gercekten_var():
    for ad in TARGETS:
        assert get_target(ad).read().strip()
    with pytest.raises(EvalError, match="optimize edilemeyen"):
        get_target("tools")


def test_override_istemi_gecici_degistirir_ve_hatada_bile_geri_koyar(monkeypatch):
    sahte = types.ModuleType("sahte_istem_modulu")
    sahte.METIN = "asıl"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sahte_istem_modulu", sahte)
    hedef = PromptTarget("x", Path("yok"), "sahte_istem_modulu", "METIN")
    with override(hedef, "aday"):
        assert sahte.METIN == "aday"  # type: ignore[attr-defined]
    assert sahte.METIN == "asıl"  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError), override(hedef, "aday"):
        raise RuntimeError("patladı")
    assert sahte.METIN == "asıl"  # type: ignore[attr-defined]


async def test_override_runner_ic_koşucuyu_aday_istemle_calistirir(monkeypatch):
    sahte = types.ModuleType("sahte_istem_modulu2")
    sahte.METIN = "asıl"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sahte_istem_modulu2", sahte)
    hedef = PromptTarget("x", Path("yok"), "sahte_istem_modulu2", "METIN")
    gorulen: list[str] = []

    class _Ic:
        async def run(self, request, *, root, strict_approval=False, transcript=None):
            gorulen.append(sahte.METIN)  # type: ignore[attr-defined]
            return "gözlem"

    sonuc = await PromptOverrideRunner(_Ic(), hedef, "aday").run("istek", root=Path())  # type: ignore[arg-type]
    assert (sonuc, gorulen, sahte.METIN) == ("gözlem", ["aday"], "asıl")  # type: ignore[attr-defined]


async def test_suite_evaluator_istem_metnini_fabrikaya_verir():
    from evals.execution import TaskExecution

    gorulen: list[str] = []

    class _Yurutucu:
        def __init__(self, metin: str) -> None:
            self._metin = metin

        async def run(self, task):
            gorulen.append(self._metin)
            return TaskExecution(
                task_id=task.id, output_text="tamam" if self._metin == "iyi" else ""
            )

    degerlendirici = SuiteEvaluator(_kume("a", "b"), lambda metin: _Yurutucu(metin))
    assert (await degerlendirici.evaluate("iyi")).task_success_rate == 1.0
    assert (await degerlendirici.evaluate("kotu")).task_success_rate == 0.0
    assert gorulen == ["iyi", "iyi", "kotu", "kotu"]


class _SahteModel:
    label = "sahte"

    def __init__(self, sonuc: ModelResult) -> None:
        self._sonuc = sonuc
        self.istekler: list[str] = []

    async def complete(self, request):
        self.istekler.append(request.messages[0].content)
        return self._sonuc

    def stream(self, request):  # pragma: no cover - kullanılmaz
        raise NotImplementedError


def _sonuc(metin: str, *, ok: bool = True, hata: str | None = None) -> ModelResult:
    return ModelResult(name="m", model="x", text=metin, latency_ms=1, ok=ok, error=hata)


async def test_model_saglayicisi_ayiriciya_gore_boler_ve_istegi_kurar():
    model = _SahteModel(_sonuc("birinci madde\n=====\nikinci madde\n=====\n"))
    saglayici = ModelSnippetProvider(model, temperature=0.4, max_tokens=500, timeout_s=30)
    ekler = await saglayici.propose(TEMEL, (FailureNote("g1", "login testini düzelt"),), 2)
    assert ekler == ("birinci madde", "ikinci madde")
    assert "g1: login testini düzelt" in model.istekler[0]
    assert TEMEL in model.istekler[0]
    assert "{ISTEM}" not in model.istekler[0]


async def test_model_hatasi_sessizce_bos_sonuca_cevrilmez():
    model = _SahteModel(_sonuc("", ok=False, hata="429"))
    saglayici = ModelSnippetProvider(model, temperature=0.4, max_tokens=500, timeout_s=30)
    with pytest.raises(EvalError, match="429"):
        await saglayici.propose(TEMEL, (), 2)


def test_istek_sablonu_ve_ayristirma():
    assert parse_snippets("a\n=====\n\n=====\nb") == ("a", "b")
    assert "başarısız görev bilgisi yok" in build_request(TEMEL, (), 1)


async def test_ayri_kume_basari_orani_dusuyorsa_oneri_olmaz(tmp_path):
    """Kimlikler kesişmese de oran düşüşü yakalanır (karşılaştırma ortak kimliğe bakar)."""
    aday = _aday()
    opt = _SahteDegerlendirici(
        {
            TEMEL: {"a": True, "b": False, "c": False, "d": False},
            aday: {"a": True, "b": True, "c": True, "d": True},
        }
    )
    ayri = _SahteDegerlendirici({TEMEL: {"x": True, "y": True, "z": True}, aday: {"q": False}})
    sonuc = await run_round(
        _kurulum(tmp_path),
        provider=_SahteSaglayici(("Her değişiklikten sonra testi çalıştır.",)),
        opt_evaluator=opt,
        heldout_evaluator=ayri,
        store=ProposalStore(tmp_path / "o"),
    )
    assert sonuc.outcome == OUTCOME_HELDOUT_REGRESSION
    assert "düştü" in sonuc.detail
