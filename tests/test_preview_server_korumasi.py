"""Önizleme sunucusu proje içindeki gizli dosyaları sunmaz (T2-04).

Ölçüldü (29 Ekim): `GET /.fusion/onizleme-giris.txt` WordPress yönetici parolasını,
`/.env` ve `/.git/config` içeriğini düz metin döndürüyordu (statik sunucu ve `php -S`);
Host başlığı da denetlenmediği için DNS yeniden bağlama ile başka bir sayfa okuyabilirdi.
"""

from __future__ import annotations

import http.client
import shutil
from pathlib import Path

import pytest

from fusion_cli.tools import preview_server
from fusion_cli.tools.preview_server import PreviewKind

PHP = shutil.which("php") or next(
    (p for p in ("/opt/homebrew/bin/php", "/usr/local/bin/php") if Path(p).is_file()), None
)
php_gerekli = pytest.mark.skipif(PHP is None, reason="php kurulu değil")


@pytest.fixture(autouse=True)
def _sunuculari_kapat():
    yield
    preview_server.stop_all()


def _kur(root: Path) -> None:
    (root / ".fusion").mkdir()
    (root / ".fusion" / "onizleme-giris.txt").write_text("Parola: GIZLI-PAROLA", encoding="utf-8")
    (root / ".env").write_text("ANAHTAR=GIZLI-ANAHTAR", encoding="utf-8")
    (root / "index.html").write_text("<html><body>HERKESE-ACIK</body></html>", encoding="utf-8")
    (root / "index.php").write_text("<?php echo 'PHP-ACIK';", encoding="utf-8")


def _get(port: int, yol: str, host: str | None = None) -> tuple[int, str]:
    baglanti = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        baglanti.putrequest("GET", yol, skip_host=host is not None)
        if host is not None:
            baglanti.putheader("Host", host)
        baglanti.endheaders()
        yanit = baglanti.getresponse()
        return yanit.status, yanit.read().decode("utf-8", "replace")
    finally:
        baglanti.close()


GIZLI_YOLLAR = [
    "/.fusion/onizleme-giris.txt",
    "/%2efusion/onizleme-giris.txt",
    "/.env",
    "/index.html/../.env",
]


@pytest.mark.parametrize("yol", GIZLI_YOLLAR)
async def test_statik_sunucu_nokta_dosyalarini_sunmaz(tmp_path, yol):
    _kur(tmp_path)
    port = preview_server.free_port()
    await preview_server.start(tmp_path, PreviewKind.STATIC, port, php=None, entry="index.html")

    durum, govde = _get(port, yol)

    assert durum == 403 and "GIZLI" not in govde


async def test_statik_sunucu_acik_dosyayi_sunmaya_devam_eder(tmp_path):
    _kur(tmp_path)
    port = preview_server.free_port()
    await preview_server.start(tmp_path, PreviewKind.STATIC, port, php=None, entry="index.html")

    durum, govde = _get(port, "/index.html")
    durum_localhost, _ = _get(port, "/index.html", host=f"localhost:{port}")

    assert durum == 200 and "HERKESE-ACIK" in govde
    assert durum_localhost == 200


async def test_statik_sunucu_yerel_olmayan_host_basligini_reddeder(tmp_path):
    _kur(tmp_path)
    port = preview_server.free_port()
    await preview_server.start(tmp_path, PreviewKind.STATIC, port, php=None, entry="index.html")

    durum, govde = _get(port, "/index.html", host=f"saldirgan.example:{port}")

    assert durum == 403 and "HERKESE-ACIK" not in govde


@php_gerekli
@pytest.mark.parametrize("yol", GIZLI_YOLLAR)
async def test_php_sunucusu_nokta_dosyalarini_sunmaz(tmp_path, yol):
    _kur(tmp_path)
    port = preview_server.free_port()
    await preview_server.start(tmp_path, PreviewKind.PHP, port, php=PHP)

    durum, govde = _get(port, yol)

    assert durum == 403 and "GIZLI" not in govde


@php_gerekli
async def test_php_sunucusu_sayfayi_ve_guzel_adresi_sunmaya_devam_eder(tmp_path):
    _kur(tmp_path)
    port = preview_server.free_port()
    await preview_server.start(tmp_path, PreviewKind.PHP, port, php=PHP)

    durum, govde = _get(port, "/")
    durum_guzel, govde_guzel = _get(port, "/urunler/ayakkabi")
    durum_host, _ = _get(port, "/", host=f"saldirgan.example:{port}")

    assert durum == 200 and "PHP-ACIK" in govde
    assert durum_guzel == 200 and "PHP-ACIK" in govde_guzel
    assert durum_host == 403


def test_kimlik_dosyasi_olusturulurken_bile_yalniz_sahibe_aciktir(tmp_path, monkeypatch):
    from fusion_cli.tools import wordpress_setup

    kipler: list[int] = []
    asil = wordpress_setup.os.open

    def _izle(path, flags, mode=0o777, **kwargs):
        kipler.append(mode)
        return asil(path, flags, mode, **kwargs)

    monkeypatch.setattr(wordpress_setup.os, "open", _izle)

    wordpress_setup.write_credentials(tmp_path, "http://127.0.0.1:8770", "parola-x")

    yol = tmp_path / wordpress_setup.CREDENTIALS_FILE
    assert yol.stat().st_mode & 0o777 == 0o600
    assert kipler == [0o600], "dosya geniş izinle açılıp sonradan kısıldı"


# --- Dalga 4 (T2-28b) ---------------------------------------------------------------------


async def test_mevcut_sitede_tum_eklentiler_kullanici_izni_olmadan_etkinlestirilmez(
    tmp_path, monkeypatch
):
    """`plugin activate --all` bilerek devre dışı bırakılmış eklentileri (Wordfence) açıyordu."""
    from fusion_cli.tools import wordpress_setup

    cagrilar: list[tuple] = []

    async def _wp(wp_cli, root, *args):
        cagrilar.append(args)

    async def _run(wp_cli, root, *args):
        cagrilar.append(args)
        return 0, ""

    monkeypatch.setattr(wordpress_setup, "_wp", _wp)
    monkeypatch.setattr(wordpress_setup, "run_wp", _run)

    await wordpress_setup._plugins("wp", tmp_path, [], [], fresh=False)
    assert ("plugin", "activate", "--all") not in cagrilar

    await wordpress_setup._plugins("wp", tmp_path, [], [], fresh=True)
    assert ("plugin", "activate", "--all") in cagrilar
