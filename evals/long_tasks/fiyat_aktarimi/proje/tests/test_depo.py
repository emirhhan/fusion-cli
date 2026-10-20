from stokapp.depo import UrunDeposu
from stokapp.models import Urun


def test_kaydet_ve_oku(tmp_path):
    depo = UrunDeposu(tmp_path / "u.json")
    depo.kaydet({"A1": Urun("A1", "Kask", 1000, 1500)})
    assert depo.hepsi()["A1"].ad == "Kask"
