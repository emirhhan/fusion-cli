"""Önizleme panelinde https://localhost (P-041 kalanı).

Ölçüldü (31 Ekim): `https://localhost:8443` (mkcert/Vite basicSsl) panelde "yalnız localhost
adresleri" hatası veriyordu; denetim şemayı `http` ile sınırlıyordu. Yerel sertifikalar çoğu
zaman kendinden imzalıdır: doğrulama ve başsız günlük yalnız LOOPBACK için sertifikayı
sorgulamaz (uzak https yine panelde açılmaz).
"""

from __future__ import annotations

import datetime
import http.server
import os
import ssl
import threading
from pathlib import Path

import pytest

from fusion_cli.appserver.web_preview import is_local_preview_url, validate_web_preview
from fusion_cli.tools import preview_server
from fusion_cli.tools.preview_launch import is_local_url
from fusion_cli.tools.preview_log import CaptureOptions, collect_page_log


def _sertifika(klasor: Path) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    anahtar = ec.generate_private_key(ec.SECP256R1())
    ad = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    simdi = datetime.datetime.now(datetime.UTC)
    sertifika = (
        x509.CertificateBuilder()
        .subject_name(ad)
        .issuer_name(ad)
        .public_key(anahtar.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(simdi - datetime.timedelta(days=1))
        .not_valid_after(simdi + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(anahtar, hashes.SHA256())
    )
    pem = klasor / "sertifika.pem"
    key = klasor / "anahtar.pem"
    pem.write_bytes(sertifika.public_bytes(serialization.Encoding.PEM))
    key.write_bytes(
        anahtar.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return pem, key


class _Sayfa(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        govde = b"<!doctype html><title>tls</title><script>console.error('tls-hata')</script>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *_args: object) -> None:
        return None


@pytest.fixture
def https_sunucu(tmp_path):
    pem, key = _sertifika(tmp_path)
    sunucu = http.server.ThreadingHTTPServer(("127.0.0.1", preview_server.free_port()), _Sayfa)
    baglam = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    baglam.load_cert_chain(pem, key)
    sunucu.socket = baglam.wrap_socket(sunucu.socket, server_side=True)
    is_parcacigi = threading.Thread(target=sunucu.serve_forever, daemon=True)
    is_parcacigi.start()
    yield f"https://localhost:{sunucu.server_address[1]}/"
    sunucu.shutdown()
    sunucu.server_close()


def test_https_loopback_yerel_sayilir_uzak_https_sayilmaz():
    for adres in ("https://localhost:8443/", "https://127.0.0.1:8443/x", "https://[::1]:8443/"):
        assert is_local_preview_url(adres) and is_local_url(adres)
    for adres in ("https://example.com/", "https://192.168.1.2:8443/", "ftp://localhost/"):
        assert not is_local_preview_url(adres) and not is_local_url(adres)


def test_kendinden_imzali_yerel_https_dogrulanir(https_sunucu):
    sonuc = validate_web_preview({"url": https_sunucu})
    assert sonuc["ok"] is True and sonuc["url"] == https_sunucu


def _playwright_hazir() -> bool:
    try:
        import playwright.async_api  # noqa: F401
    except ImportError:
        return False
    cache = Path(
        os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / "Library/Caches/ms-playwright"
    )
    return any(cache.glob("chromium*")) if cache.is_dir() else False


@pytest.mark.skipif(not _playwright_hazir(), reason="Playwright/Chromium kurulu değil")
async def test_yerel_https_sayfanin_konsolu_okunur(https_sunucu):
    log = await collect_page_log(https_sunucu, CaptureOptions(settle_ms=100))
    assert log.error == ""
    assert any("tls-hata" in entry.text for entry in log.console)


def test_paket_csp_yerel_httpsi_cerceveler_uzak_httpsi_cercevelemez():
    import json

    conf = json.loads(
        (Path(__file__).parents[1] / "app" / "src-tauri" / "tauri.conf.json").read_text("utf-8")
    )

    def _csp_bloklari(dugum: object):
        if isinstance(dugum, dict):
            if isinstance(dugum.get("frame-src"), str):
                yield dugum["frame-src"]
            for deger in dugum.values():
                yield from _csp_bloklari(deger)

    bloklar = list(_csp_bloklari(conf))
    assert len(bloklar) >= 2
    for frame in bloklar:
        kaynaklar = frame.split()
        assert "https://localhost:*" in kaynaklar and "https://127.0.0.1:*" in kaynaklar
        assert "https:" not in kaynaklar and "*" not in kaynaklar
