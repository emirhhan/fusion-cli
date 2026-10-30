"""Uzak eşleştirme verisi Fusion veri dizininde durur; eski `~/remote` otomatik taşınır.

Ölçüldü (30 Ekim): `RemoteController` `home / "remote"` kullanıyordu; gerçek kullanıcıda bu
`~/remote/devices.json` + `projects.json` üretiyordu (ev dizini kirlenmesi). Gerçek `~/remote`
ve gerçek veri dizinine dokunulmaz: her şey tmp_path altında.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from fusion_cli.config.paths import base_data_dir
from fusion_cli.remote import data_dir as remote_data
from fusion_cli.remote.controller import RemoteController


def _eski(tmp_path: Path) -> Path:
    legacy = tmp_path / "ev" / "remote"
    legacy.mkdir(parents=True)
    (legacy / "devices.json").write_text('{"devices": ["telefon"]}')
    (legacy / "projects.json").write_text('{"roots": []}')
    for dosya in legacy.iterdir():
        dosya.chmod(0o600)  # gerçek kullanıcıdaki gibi: cihaz sırları yalnız sahibine açık
    return legacy


def test_hedef_fusion_veri_dizinidir():
    assert remote_data.remote_data_dir() == base_data_dir() / "remote"


def test_eski_dosyalar_dogrulanarak_tasinir_ve_migrated_olur(tmp_path):
    legacy = _eski(tmp_path)
    hedef = tmp_path / "veri" / "remote"

    tasinan = remote_data.migrate_legacy(legacy, hedef)

    assert sorted(tasinan) == ["devices.json", "projects.json"]
    assert (hedef / "devices.json").read_text() == '{"devices": ["telefon"]}'
    assert (hedef / "devices.json").stat().st_mode & 0o777 == 0o600
    assert not (legacy / "devices.json").exists()
    assert (legacy / "devices.json.migrated").read_text() == '{"devices": ["telefon"]}'


def test_goc_idempotenttir(tmp_path):
    legacy = _eski(tmp_path)
    hedef = tmp_path / "veri" / "remote"
    remote_data.migrate_legacy(legacy, hedef)
    assert remote_data.migrate_legacy(legacy, hedef) == []
    assert (hedef / "devices.json").exists()
    assert (legacy / "devices.json.migrated").exists()


def test_iki_yerde_de_varsa_yeni_kullanilir_eskiye_dokunulmaz_ve_uyarilir(tmp_path, caplog):
    legacy = _eski(tmp_path)
    hedef = tmp_path / "veri" / "remote"
    hedef.mkdir(parents=True)
    (hedef / "devices.json").write_text('{"devices": ["yeni"]}')

    with caplog.at_level(logging.WARNING):
        tasinan = remote_data.migrate_legacy(legacy, hedef)

    assert tasinan == ["projects.json"]
    assert (hedef / "devices.json").read_text() == '{"devices": ["yeni"]}'
    assert (legacy / "devices.json").read_text() == '{"devices": ["telefon"]}'
    assert any("devices.json" in kayit.getMessage() for kayit in caplog.records)


def test_ayni_icerikli_yarim_kalmis_goc_sessizce_tamamlanir(tmp_path, caplog):
    legacy = _eski(tmp_path)
    hedef = tmp_path / "veri" / "remote"
    hedef.mkdir(parents=True)
    (hedef / "devices.json").write_text('{"devices": ["telefon"]}')

    with caplog.at_level(logging.WARNING):
        remote_data.migrate_legacy(legacy, hedef)

    assert (legacy / "devices.json.migrated").exists()
    assert not caplog.records


def test_dogrulama_basarisizsa_eski_dosya_korunur(tmp_path, monkeypatch):
    legacy = _eski(tmp_path)
    hedef = tmp_path / "veri" / "remote"

    def bozuk_kopya(kaynak, hedef_yol, **_):
        Path(hedef_yol).write_text("yarim")
        return hedef_yol

    monkeypatch.setattr(remote_data.shutil, "copy2", bozuk_kopya)

    assert remote_data.migrate_legacy(legacy, hedef) == []
    assert (legacy / "devices.json").read_text() == '{"devices": ["telefon"]}'
    assert not (hedef / "devices.json").exists()
    assert not list(hedef.glob("*.tmp*"))


def test_yukleme_klasoru_ve_sqlite_tasinir(tmp_path):
    legacy = _eski(tmp_path)
    (legacy / "uploads").mkdir()
    (legacy / "uploads" / "a-foto.png").write_bytes(b"png")
    veritabani = sqlite3.connect(legacy / "runs.sqlite3")
    veritabani.execute("create table t (x integer)")
    veritabani.execute("insert into t values (7)")
    veritabani.commit()
    veritabani.close()
    hedef = tmp_path / "veri" / "remote"

    remote_data.migrate_legacy(legacy, hedef)

    assert (hedef / "uploads" / "a-foto.png").read_bytes() == b"png"
    assert (legacy / "uploads.migrated" / "a-foto.png").exists()
    kopya = sqlite3.connect(hedef / "runs.sqlite3")
    assert kopya.execute("select x from t").fetchall() == [(7,)]
    kopya.close()
    assert (legacy / "runs.sqlite3.migrated").exists()


def test_eski_dizin_yoksa_hicbir_sey_olmaz(tmp_path):
    assert remote_data.migrate_legacy(tmp_path / "yok", tmp_path / "veri" / "remote") == []
    assert not (tmp_path / "veri").exists()


class _Sirlar:
    available = True

    def get(self, name: str) -> str | None:
        return None

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> bool:
        return False


async def test_denetleyici_eski_eslesmis_telefonu_veri_dizininden_okur(tmp_path):
    legacy = _eski(tmp_path)
    ev = legacy.parent
    controller: Any = RemoteController(
        home=ev,
        root=tmp_path,
        secrets=_Sirlar(),
        session_factory=lambda writer: object(),
    )
    try:
        veri = base_data_dir() / "remote"
        assert json.loads((veri / "devices.json").read_text()) == {"devices": ["telefon"]}
        assert not (ev / "remote" / "devices.json").exists()
        assert controller._directory == veri
    finally:
        await controller.aclose()


async def test_denetleyici_ev_dizinine_remote_olusturmaz(tmp_path):
    ev = tmp_path / "ev"
    ev.mkdir()
    controller: Any = RemoteController(
        home=ev,
        root=tmp_path,
        secrets=_Sirlar(),
        session_factory=lambda writer: object(),
    )
    try:
        await controller.dispatch("uzak.eslestir_baslat", {})
        assert not (ev / "remote").exists()
    finally:
        await controller.aclose()
