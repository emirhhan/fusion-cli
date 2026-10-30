"""woo_import.php: kök dışı görsel kopyalanmaz, fiyatsız ürün yayına girmez, bozuk JSON bildirilir (Z1-60).

Ölçüldü (30 Ekim): `$kok . '/' . $veri['gorsel']` normalize edilmeden birleşiyordu (`../` kökün
dışındaki dosyayı ortam kitaplığına kopyalar); sayısal olmayan fiyat atlanıp ürün fiyatsız "publish"
oluyordu; bozuk/yok JSON sessizce 0 ürün veya uyarı veriyordu. WordPress yerine sahte ortamla çalışır.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

STUB = Path(__file__).with_name("assets_php") / "woo_stub.php"

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="php gerekli")


def _calistir(tmp_path: Path, katalog: object | str, *, kok_var: bool = True) -> dict[str, Any]:
    abspath = tmp_path / "wp"
    (abspath / "wp-admin/includes").mkdir(parents=True)
    for ad in ("media", "file", "image"):
        (abspath / f"wp-admin/includes/{ad}.php").write_text("<?php\n")
    json_yolu = tmp_path / "urunler.json"
    json_yolu.write_text(katalog if isinstance(katalog, str) else json.dumps(katalog))
    kok = tmp_path / "proje"
    if kok_var:
        kok.mkdir(exist_ok=True)
    sonuc = subprocess.run(
        ["php", str(STUB), str(abspath), str(json_yolu), str(kok)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(sonuc.stdout.strip().splitlines()[-1])


def test_kok_disina_cikan_gorsel_yolu_kopyalanmaz(tmp_path: Path) -> None:
    (tmp_path / "proje").mkdir()
    (tmp_path / "proje/img.jpg").write_bytes(b"x")
    (tmp_path / "gizli.jpg").write_bytes(b"x")  # kökün DIŞINDA
    sonuc = _calistir(
        tmp_path,
        [
            {
                "ad": "Kask",
                "fiyat_sayi": 100,
                "gorsel": "img.jpg",
                "galeri": ["img.jpg", "../gizli.jpg"],
            },
            {"ad": "Eldiven", "fiyat_sayi": 50, "gorsel": "../gizli.jpg"},
        ],
    )
    assert sonuc["gorseller"] == ["img.jpg"]
    assert json.loads(sonuc["cikti"]) == {"eklenen": 2, "atlanan": 0, "gorselsiz": 1, "fiyatsiz": 0}


def test_sayisal_olmayan_fiyat_urunu_taslak_birakir(tmp_path: Path) -> None:
    sonuc = _calistir(
        tmp_path,
        [
            {"ad": "Fiyatli", "fiyat_sayi": 12.5},
            {"ad": "Virgullu", "fiyat_sayi": "1.299,00"},
            {"ad": "Fiyatsiz"},
        ],
    )
    assert sonuc["urunler"]["Fiyatli"]["durum"] == "publish"
    assert sonuc["urunler"]["Virgullu"]["durum"] == "draft"
    assert sonuc["urunler"]["Fiyatsiz"]["durum"] == "draft"
    assert json.loads(sonuc["cikti"])["fiyatsiz"] == 2


def test_bozuk_json_hata_olarak_bildirilir(tmp_path: Path) -> None:
    sonuc = _calistir(tmp_path, "{bozuk")
    hata = json.loads(sonuc["cikti"])["hata"]
    assert "çözümlenemedi" in hata
    assert not sonuc["urunler"]


def test_eksik_kok_klasoru_hata_olarak_bildirilir(tmp_path: Path) -> None:
    sonuc = _calistir(tmp_path, [], kok_var=False)
    assert "kök klasör yok" in json.loads(sonuc["cikti"])["hata"]


def test_python_tarafi_fiyatsiz_sayisini_okur() -> None:
    from fusion_cli.tools.woo_import import parse_import_output

    sonuc = parse_import_output('{"eklenen": 3, "atlanan": 0, "gorselsiz": 1, "fiyatsiz": 2}')
    assert (sonuc.added, sonuc.without_price) == (3, 2)
