"""Gizli kabul testleri: ajan görmez, görev bittikten sonra çalışma alanında koşulur."""

import subprocess
import sys

import pytest
from stokapp.depo import UrunDeposu
from stokapp.models import Urun


@pytest.fixture
def depo(tmp_path):
    d = UrunDeposu(tmp_path / "urunler.json")
    d.kaydet(
        {
            "KASK1": Urun("KASK1", "Kask", maliyet=2000, fiyat=3000),
            "ELD1": Urun("ELD1", "Eldiven", maliyet=950, fiyat=1400),
            "MNT1": Urun("MNT1", "Mont", maliyet=5000, fiyat=7000),
        }
    )
    return d


def _csv(tmp_path, satirlar):
    yol = tmp_path / "liste.csv"
    yol.write_text("sku,liste_fiyati\n" + "\n".join(satirlar) + "\n", encoding="utf-8")
    return yol


# --- olumlu işlev ---


def test_kural_ve_yuvarlama():
    from stokapp.fiyatlama import satis_fiyati

    assert satis_fiyati(3125, 2000) == 3000  # 3000.0
    assert satis_fiyati(1000, 900) == 960  # 960.0
    assert satis_fiyati(1302.6, 900) == 1250  # 1250.496 -> 1250
    assert satis_fiyati(1303.2, 900) == 1251  # 1251.07 -> 1251
    assert satis_fiyati(1000, 990.2) == 991  # maliyet tabanı, yukarı tam TL


def test_gecerli_liste_tum_urunleri_gunceller(depo, tmp_path):
    from stokapp.aktarim import fiyatlari_aktar

    sonuc = fiyatlari_aktar(depo, _csv(tmp_path, ["KASK1,3125", "ELD1,1000"]))
    assert sorted(sonuc.guncellenen) == ["ELD1", "KASK1"]
    assert sonuc.hatalar == []
    urunler = depo.hepsi()
    assert urunler["KASK1"].fiyat == 3000
    assert urunler["ELD1"].fiyat == 960
    assert urunler["MNT1"].fiyat == 7000


def test_virgullu_ondalik(depo, tmp_path):
    from stokapp.aktarim import fiyatlari_aktar

    fiyatlari_aktar(depo, _csv(tmp_path, ['KASK1,"3125,0"']))
    assert depo.hepsi()["KASK1"].fiyat == 3000


def test_cli_basarili(depo, tmp_path):
    csv = _csv(tmp_path, ["MNT1,8000"])
    p = subprocess.run(
        [sys.executable, "-m", "stokapp.cli", "--depo", str(depo.yol), "fiyat-aktar", str(csv)],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr
    assert depo.hepsi()["MNT1"].fiyat == 7680


# --- olumsuz / atomiklik ---


@pytest.mark.parametrize("kotu", ["YOK99,1000", "KASK1,-5", "KASK1,", "KASK1,abc"])
def test_tek_hatali_satir_hicbir_seyi_guncellemez(depo, tmp_path, kotu):
    from stokapp.aktarim import fiyatlari_aktar

    sonuc = fiyatlari_aktar(depo, _csv(tmp_path, ["ELD1,1000", kotu]))
    assert sonuc.guncellenen == []
    assert sonuc.hatalar and any("3" in h for h in sonuc.hatalar)  # veri satırı 2 = dosya satırı 3
    assert depo.hepsi()["ELD1"].fiyat == 1400


def test_cli_hatada_cikis_1_ve_degisiklik_yok(depo, tmp_path):
    csv = _csv(tmp_path, ["MNT1,8000", "YOK,1"])
    p = subprocess.run(
        [sys.executable, "-m", "stokapp.cli", "--depo", str(depo.yol), "fiyat-aktar", str(csv)],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 1
    assert depo.hepsi()["MNT1"].fiyat == 7000
