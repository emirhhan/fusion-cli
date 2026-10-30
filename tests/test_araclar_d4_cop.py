"""Çöp (safe_delete) bütünlüğü ve jobs günlük kuyruğu (T2-18, T2-19)."""

from __future__ import annotations

import json
import os
import time

import pytest

from fusion_cli.tools import safe_delete
from fusion_cli.tools.safe_delete import forbidden_reason, list_trash, move_to_trash, restore


@pytest.fixture
def alan(tmp_path):
    ev = tmp_path / "ev"
    proje = ev / "proje"
    cop = tmp_path / "cop"
    proje.mkdir(parents=True)
    return ev, proje, cop


def _sil(hedef, proje, ev, cop):
    return move_to_trash((str(hedef),), cwd=proje, root=proje, home=ev, trash_root=cop)


def test_sembolik_bag_silinince_asil_yol_bagin_kendisidir(alan):
    """T2-18a: kayıtlı "asıl yol" bağın HEDEFİ oluyor, geri yükleme yanlış yerde patlıyordu."""
    ev, proje, cop = alan
    gercek = proje / "gercek.txt"
    gercek.write_text("x", encoding="utf-8")
    bag = proje / "bag"
    bag.symlink_to(gercek)

    moved, _ = _sil(bag, proje, ev, cop)

    assert moved[0].original == bag.absolute()
    assert gercek.exists()
    restore(cop, moved[0].id)
    assert bag.is_symlink() and gercek.read_text(encoding="utf-8") == "x"


def test_eve_isaret_eden_baglanti_silinebilir(alan):
    """T2-18e: `rm link` (link -> ev dizini) bağı siler, ev dizinini değil; reddedilmemeli."""
    ev, proje, cop = alan
    bag = proje / "evbagi"
    bag.symlink_to(ev)

    assert forbidden_reason(bag, ev, cop) is None
    assert forbidden_reason(ev, ev, cop) is not None


def test_bozuk_manifest_diger_silmeleri_durdurmaz(alan):
    """T2-18c: manifestte anahtar eksikse KeyError tüm silmeyi ve `fusion cop`'u çökertiyordu."""
    ev, proje, cop = alan
    bozuk = cop / "20200101-000000-aaaaaa"
    bozuk.mkdir(parents=True)
    (bozuk / safe_delete._MANIFEST).write_text(json.dumps({"yanlis": 1}), encoding="utf-8")
    (bozuk / "x.txt").write_text("x", encoding="utf-8")
    dosya = proje / "a.txt"
    dosya.write_text("a", encoding="utf-8")

    moved, _ = _sil(dosya, proje, ev, cop)

    assert len(moved) == 1
    assert [e.id for e in list_trash(cop)] == [moved[0].id]


def test_manifest_tasimadan_once_yazilir(alan, monkeypatch):
    """T2-18b: taşıma sonrası çökme manifestsiz yetim klasör bırakıyordu."""
    ev, proje, cop = alan
    dosya = proje / "a.txt"
    dosya.write_text("a", encoding="utf-8")

    def _coker(*_a, **_k):
        raise OSError("taşıma çöktü")

    monkeypatch.setattr(safe_delete.shutil, "move", _coker)
    with pytest.raises(OSError):
        _sil(dosya, proje, ev, cop)

    (klasor,) = list(cop.iterdir())
    assert (klasor / safe_delete._MANIFEST).exists()
    assert dosya.exists()


def test_suresi_dolan_yetim_klasor_temizlenir(alan):
    """Manifestsiz yetim klasör hiç temizlenmiyordu (kalıcı sızıntı)."""
    ev, proje, cop = alan
    yetim = cop / "20200101-000000-bbbbbb"
    yetim.mkdir(parents=True)
    (yetim / "x.txt").write_text("x", encoding="utf-8")
    eski = time.time() - (safe_delete.TRASH_RETENTION_DAYS + 1) * 86_400
    os.utime(yetim, (eski, eski))
    dosya = proje / "a.txt"
    dosya.write_text("a", encoding="utf-8")

    _sil(dosya, proje, ev, cop)

    assert not yetim.exists()


def test_job_gunlugu_kuyrugu_tum_dosyayi_okumaz(tmp_path, monkeypatch):
    """T2-19: her `job_status` tüm .log'u `read_text` ile belleğe alıyordu."""
    from pathlib import Path as _Path

    from fusion_cli.tools import jobs

    log = tmp_path / "j1.log"
    log.write_text("a" * 500_000 + "SON-SATIR-ğüş\n", encoding="utf-8")
    okunan: list[int] = []
    gercek_read_text = _Path.read_text

    def _izle(self, *a, **k):
        if self == log:
            raise AssertionError("tüm dosya read_text ile okundu")
        return gercek_read_text(self, *a, **k)

    monkeypatch.setattr(_Path, "read_text", _izle)

    cikti = jobs._tail(tmp_path, "j1")

    assert cikti.endswith("SON-SATIR-ğüş\n")
    assert len(cikti) < jobs.JOB_LOG_TAIL_CHARS + 200
    assert "atlandı" in cikti
    del okunan


def test_job_gunlugu_kisa_ise_oldugu_gibi(tmp_path):
    from fusion_cli.tools import jobs

    (tmp_path / "j2.log").write_text("merhaba\n", encoding="utf-8")

    assert jobs._tail(tmp_path, "j2") == "merhaba\n"
    assert jobs._tail(tmp_path, "yok") == ""
