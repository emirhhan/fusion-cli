"""Sayfa gürültüsü ayıklayıcısı model cevabındaki dosya adı satırlarını silmez (P1-01).

Ölçüldü (29 Ekim): `_CITATION_LINE` tek başına duran her `ad.uzanti` satırını alan adı sayıp
siliyordu. `README.md`, `main.py`, `docker-compose.yml`, `app.py - ana giriş` gibi satırlar
bir `write_file` içeriğinde (dosya ağacı, `.gitignore`, MANIFEST) cevaptan kayboluyordu;
`.md`/`.py`/`.sh`/`.rs` aynı zamanda geçerli ülke alan adı uzantılarıdır.
"""

from __future__ import annotations

import pytest

from fusion_cli.providers.web_browser import strip_page_noise, strip_role_headers

DOSYA_SATIRLARI = [
    "README.md",
    "main.py",
    "requirements.txt",
    "docker-compose.yml",
    "index.html",
    "secrets.json",
    "app.py - ana giriş",
    "Cargo.toml",
    "build.rs",
    "deploy.sh",
    "player.gd",
    "main.tscn",
]


@pytest.mark.parametrize("satir", DOSYA_SATIRLARI)
def test_dosya_adi_satiri_cevaptan_silinmez(satir):
    cevap = f"icerik:\n{satir}\nson"

    assert satir in strip_page_noise(cevap)
    assert satir in strip_role_headers(cevap)


@pytest.mark.parametrize(
    "cip",
    [
        "erlas.com.tr",
        "COGNOiSe.com - The IBM Cognos Community",
        "https://example.org/a/b",
        "bbc.co.uk",
    ],
)
def test_atif_cipi_satiri_hala_ayiklanir(cip):
    sonuc = strip_page_noise(f"Cevap metni.\n{cip}")

    assert cip not in sonuc
    assert "Cevap metni." in sonuc
