"""Taslak deposu, küme çözümü ve onaylı kabul: taslak ASLA kendiliğinden kümeye girmez."""

from __future__ import annotations

import pytest
from evals.dongu_kaydi import kayit_ekle, kayitlari_oku
from evals.kume import (
    kabul_edilen_kimlikler,
    kume_coz,
    olcut_olustur,
    taslagi_kabul_et,
)
from evals.loader import load_tasks, task_to_mapping
from evals.tasks import CriterionKind, EvalTask, SuccessCriterion
from evals.taslak import Taslak, TaslakKaynagi
from evals.taslak_deposu import TaslakDeposu

from fusion_cli.core.errors import EvalError


def _taslak(kimlik="tk-0123456789", olcut=None, istek="login.py parola kontrolünü düzelt"):
    return Taslak(
        id=kimlik,
        kaynak=TaslakKaynagi.DUZELTME,
        request=istek,
        olcut=olcut,
        olcut_notu="not",
        kanit=("kullanıcı mesajı: «hayır»",),
        olusturma="2026-10-30T10:00:00+00:00",
    )


_OLCUT = SuccessCriterion(kind=CriterionKind.EXIT_CODE, expected_exit_code=0, command="pytest -q")


def test_kaydet_listele_oku_gidis_donus(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    depo.kaydet([_taslak(olcut=_OLCUT)])
    (okunan,) = depo.listele()
    assert okunan == _taslak(olcut=_OLCUT)
    assert depo.oku("tk-0123456789").olcut == _OLCUT


def test_olcutsuz_taslak_da_saklanir(tmp_path):
    depo = TaslakDeposu(tmp_path)
    depo.kaydet([_taslak()])
    assert depo.oku("tk-0123456789").olcut is None


def test_ayni_taslak_ikinci_kez_yazilmaz(tmp_path):
    depo = TaslakDeposu(tmp_path)
    assert len(depo.kaydet([_taslak()])) == 1
    assert depo.kaydet([_taslak()]) == ()


def test_atla_listesindeki_kimlik_yazilmaz(tmp_path):
    depo = TaslakDeposu(tmp_path)
    assert depo.kaydet([_taslak()], atla={"tk-0123456789"}) == ()


def test_silinen_taslak_bir_daha_onerilmez(tmp_path):
    depo = TaslakDeposu(tmp_path)
    depo.kaydet([_taslak()])
    depo.kaldir("tk-0123456789", reddet=True)
    assert depo.listele() == ()
    assert depo.kaydet([_taslak()]) == ()


def test_gecersiz_kimlik_dizin_disina_cikamaz(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    for kotu in ("../x", "tk-12", "tk-0123456789/../../a", ""):
        with pytest.raises(EvalError):
            depo.oku(kotu)


def test_olmayan_taslak_anlasilir_hata_verir(tmp_path):
    with pytest.raises(EvalError, match="böyle bir taslak yok"):
        TaslakDeposu(tmp_path).oku("tk-0123456789")


def test_bozuk_taslak_listeyi_dusurmez(tmp_path):
    depo = TaslakDeposu(tmp_path)
    depo.kaydet([_taslak()])
    (tmp_path / "tk-aaaaaaaaaa.yaml").write_text("bozuk: [", encoding="utf-8")
    assert [t.id for t in depo.listele()] == ["tk-0123456789"]


# --------------------------------------------------------------------------- #
# Kabul
# --------------------------------------------------------------------------- #


def test_kabul_gorevi_kullanici_kumesine_yazar_ve_taslagi_kaldirir(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    depo.kaydet([_taslak(olcut=_OLCUT)])
    kume = tmp_path / "kume" / "kullanici.yaml"

    gorev = taslagi_kabul_et(depo, "tk-0123456789", kume)

    assert gorev.criterion == _OLCUT
    (yuklenen,) = load_tasks(kume)
    assert yuklenen.request == "login.py parola kontrolünü düzelt"
    assert depo.listele() == ()
    assert kabul_edilen_kimlikler(kume.parent) == {"tk-0123456789"}


def test_ikinci_kabul_ayni_dosyaya_eklenir_ve_yorumlar_korunur(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    depo.kaydet(
        [_taslak(olcut=_OLCUT), _taslak("tk-aaaaaaaaaa", _OLCUT, "başka bir iş yap lütfen")]
    )
    kume = tmp_path / "kume" / "k.yaml"
    taslagi_kabul_et(depo, "tk-0123456789", kume)
    kume.write_text(kume.read_text(encoding="utf-8") + "\n# elle eklenen not\n", encoding="utf-8")
    taslagi_kabul_et(depo, "tk-aaaaaaaaaa", kume)
    assert [g.id for g in load_tasks(kume)] == ["tk-0123456789", "tk-aaaaaaaaaa"]
    assert "# elle eklenen not" in kume.read_text(encoding="utf-8")


def test_olcutsuz_taslak_kabul_edilmez_ama_olcut_verilince_edilir(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    depo.kaydet([_taslak()])
    kume = tmp_path / "kume" / "k.yaml"
    with pytest.raises(EvalError, match="ölçüt yok"):
        taslagi_kabul_et(depo, "tk-0123456789", kume)
    assert not kume.exists()
    assert len(depo.listele()) == 1  # reddedilen kabul taslağı kaybettirmez

    gorev = taslagi_kabul_et(
        depo, "tk-0123456789", kume, olcut=olcut_olustur(anahtar="parola doğrulandı")
    )
    assert gorev.criterion.kind is CriterionKind.KEYWORD


def test_olcut_secenekleri_cakisirsa_hata():
    with pytest.raises(EvalError, match="yalnız birini"):
        olcut_olustur(komut="pytest", anahtar="x")
    assert olcut_olustur() is None


def test_ayni_gorev_kumede_varsa_ikinci_kez_eklenmez(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    kume = tmp_path / "kume" / "k.yaml"
    depo.kaydet([_taslak(olcut=_OLCUT)])
    taslagi_kabul_et(depo, "tk-0123456789", kume)
    depo.kaydet([_taslak(olcut=_OLCUT)], atla=())
    with pytest.raises(EvalError, match="zaten kümede"):
        taslagi_kabul_et(depo, "tk-0123456789", kume)


def test_taslak_otomatik_kumeye_girmez(tmp_path):
    depo = TaslakDeposu(tmp_path / "taslak")
    depo.kaydet([_taslak(olcut=_OLCUT)])
    assert not (tmp_path / "kume").exists()


def test_gorev_gidis_donus_her_olcut_turu():
    for olcut in (
        _OLCUT,
        SuccessCriterion(kind=CriterionKind.KEYWORD, keyword="a", alternatives=("b",)),
        SuccessCriterion(kind=CriterionKind.FILE_UNCHANGED, expected_path="x.py"),
        SuccessCriterion(kind=CriterionKind.WORKSPACE_UNCHANGED),
    ):
        gorev = EvalTask(id="g", request="r", criterion=olcut)
        assert task_to_mapping(gorev)["criterion"]


# --------------------------------------------------------------------------- #
# Küme çözümü ve ölçüm izi
# --------------------------------------------------------------------------- #


def test_kume_coz_kullanici_kumesi_paketliyi_golgeler(tmp_path):
    kullanici, paketli = tmp_path / "k", tmp_path / "p"
    kullanici.mkdir()
    paketli.mkdir()
    (paketli / "hata.yaml").write_text("tasks: []", encoding="utf-8")
    assert (
        kume_coz("hata", kullanici_dizini=kullanici, paketli_dizin=paketli) == paketli / "hata.yaml"
    )
    (kullanici / "hata.yaml").write_text("tasks: []", encoding="utf-8")
    assert (
        kume_coz("hata", kullanici_dizini=kullanici, paketli_dizin=paketli)
        == kullanici / "hata.yaml"
    )


def test_kume_coz_olmayan_ad_bilinenleri_sayar(tmp_path):
    (tmp_path / "hata.yaml").write_text("tasks: []", encoding="utf-8")
    with pytest.raises(EvalError, match="Bilinen kümeler: hata"):
        kume_coz("yok", kullanici_dizini=tmp_path / "x", paketli_dizin=tmp_path)
    with pytest.raises(EvalError, match="geçersiz küme adı"):
        kume_coz("../etc", kullanici_dizini=tmp_path, paketli_dizin=tmp_path)


def test_kayit_dosyasi_ekler_ve_bozuk_satiri_atlar(tmp_path):
    yol = tmp_path / "izler" / "kayit.jsonl"
    kayit_ekle(yol, "taslak_uretildi", {"sayi": 3}, simdi=1_800_000_000.0)
    with yol.open("a", encoding="utf-8") as akim:
        akim.write("bozuk{\n")
    kayit_ekle(yol, "oneri", {"opt_skoru": 0.5}, simdi=1_800_000_100.0)
    kayitlar = kayitlari_oku(yol)
    assert [k["olay"] for k in kayitlar] == ["taslak_uretildi", "oneri"]
    assert kayitlar[0]["sayi"] == 3
