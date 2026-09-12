"""Tur değişikliklerinin kaydı ve geri alınması."""

from __future__ import annotations

from fusion_cli.core.changeset import ChangeSet


def test_bos_kayit_yanlistir(tmp_path):
    assert not ChangeSet()


def test_degistirilen_dosya_ilk_haline_doner(tmp_path):
    dosya = tmp_path / "a.py"
    dosya.write_text("eski\n", encoding="utf-8")
    kayit = ChangeSet()

    kayit.record(dosya)
    dosya.write_text("yeni\n", encoding="utf-8")
    kayit.restore()

    assert dosya.read_text(encoding="utf-8") == "eski\n"


def test_yeni_olusturulan_dosya_geri_alinca_silinir(tmp_path):
    dosya = tmp_path / "yeni.py"
    kayit = ChangeSet()

    kayit.record(dosya)  # henüz yok
    dosya.write_text("icerik\n", encoding="utf-8")
    kayit.restore()

    assert not dosya.exists()


def test_ikili_dosya_ilk_haline_doner(tmp_path):
    dosya = tmp_path / "asset.bin"
    dosya.write_bytes(b"\xff\xfe\x00")
    kayit = ChangeSet()

    kayit.record(dosya)
    dosya.unlink()
    kayit.restore()

    assert dosya.read_bytes() == b"\xff\xfe\x00"


def test_ayni_dosyanin_ilk_hali_saklanir(tmp_path):
    """Geri alma turun BAŞINA döner, bir önceki ara adıma değil."""
    dosya = tmp_path / "a.py"
    dosya.write_text("baslangic\n", encoding="utf-8")
    kayit = ChangeSet()

    kayit.record(dosya)
    dosya.write_text("ara\n", encoding="utf-8")
    kayit.record(dosya)
    dosya.write_text("son\n", encoding="utf-8")
    kayit.restore()

    assert dosya.read_text(encoding="utf-8") == "baslangic\n"


def test_kullanicinin_dokunulmamis_dosyalari_etkilenmez(tmp_path):
    """Kayıt yalnızca AGENT'IN dokunduğu yolları taşır."""
    agent_dosyasi = tmp_path / "agent.py"
    kullanici_dosyasi = tmp_path / "kullanici.py"
    agent_dosyasi.write_text("eski\n", encoding="utf-8")
    kullanici_dosyasi.write_text("elle yazdim\n", encoding="utf-8")
    kayit = ChangeSet()

    kayit.record(agent_dosyasi)
    agent_dosyasi.write_text("yeni\n", encoding="utf-8")
    kayit.restore()

    assert kullanici_dosyasi.read_text(encoding="utf-8") == "elle yazdim\n"


def test_commit_sonrasi_geri_alinamaz(tmp_path):
    dosya = tmp_path / "a.py"
    dosya.write_text("eski\n", encoding="utf-8")
    kayit = ChangeSet()

    kayit.record(dosya)
    dosya.write_text("yeni\n", encoding="utf-8")
    kayit.commit()
    kayit.restore()

    assert dosya.read_text(encoding="utf-8") == "yeni\n"
    assert not kayit


def test_alt_kayit_ana_kayda_ilk_hali_bozmadan_aktarilir(tmp_path):
    dosya = tmp_path / "a.py"
    dosya.write_text("ilk\n", encoding="utf-8")
    ana = ChangeSet()
    ana.record(dosya)
    dosya.write_text("ara\n", encoding="utf-8")
    alt = ChangeSet()
    alt.record(dosya)
    dosya.write_text("son\n", encoding="utf-8")

    ana.absorb(alt)
    ana.restore()

    assert dosya.read_text(encoding="utf-8") == "ilk\n"
    assert not alt


def test_bir_dosya_geri_alinamasa_da_digerleri_alinir(tmp_path, monkeypatch):
    saglam = tmp_path / "saglam.py"
    sorunlu = tmp_path / "sorunlu.py"
    saglam.write_text("eski\n", encoding="utf-8")
    sorunlu.write_text("eski\n", encoding="utf-8")
    kayit = ChangeSet()
    kayit.record(saglam)
    kayit.record(sorunlu)
    saglam.write_text("yeni\n", encoding="utf-8")

    from pathlib import Path

    gercek = Path.write_bytes

    def _secici(self, *args, **kwargs):
        if self.name == "sorunlu.py":
            raise OSError("izin yok")
        return gercek(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_bytes", _secici)

    geri_alinan = kayit.restore()

    assert saglam.read_text(encoding="utf-8") == "eski\n"
    assert saglam in geri_alinan
    assert sorunlu not in geri_alinan


def test_edinilen_dosya_geri_almada_silinmez(tmp_path):
    """İndirilen varlık, adım düşse bile diskte kalır.

    Ölçülmüş vaka: `download_file` 260 KB'lık paketi getirdi, adım doğrulaması
    düştü ve geri alma paketi sildi; sonraki deneme sıfırdan indirmek zorunda
    kaldı. Edinilen dosya agent'ın ürettiği içerik değildir.
    """
    paket = tmp_path / "assets" / "kenney.zip"
    paket.parent.mkdir()
    kayit = ChangeSet()
    paket.write_bytes(b"PK\x03\x04")
    kayit.record_acquired(paket)

    # İzlenir: kısıtlar ve raporlama dosyayı görmelidir.
    assert paket in kayit.paths
    assert kayit.was_created_this_turn(paket)

    geri_alinan = kayit.restore()

    assert paket.exists()
    assert paket not in geri_alinan


def test_yazilan_dosya_edinim_yaninda_yine_geri_alinir(tmp_path):
    paket = tmp_path / "kenney.zip"
    kod = tmp_path / "oyuncu.gd"
    paket.write_bytes(b"PK")
    kayit = ChangeSet()
    kayit.record_acquired(paket)
    kayit.record(kod)
    kod.write_text("extends Node\n", encoding="utf-8")

    geri_alinan = kayit.restore()

    assert paket.exists()
    assert not kod.exists()
    assert geri_alinan == (kod,)


def test_edinim_alt_isleme_aktarilir(tmp_path):
    paket = tmp_path / "kenney.zip"
    paket.write_bytes(b"PK")
    alt = ChangeSet()
    alt.record_acquired(paket)
    ust = ChangeSet()

    ust.absorb(alt)
    ust.restore()

    assert paket.exists()
