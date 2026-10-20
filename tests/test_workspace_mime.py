"""Dosya türü tahmini işletim sistemi kayıt defterine bağlı OLMAMALI.

Ölçüldü (Windows CI, run 34591998944): `proje.oku` isteği paketlenmiş runtime'da
30 saniyede yanıt vermedi ve Windows kurucusu hiç üretilemedi. Zincir: `proje.listele`
`_mime()` çağırmıyor ve hızlı geçiyor; `proje.oku` çağıran İLK istek ve `mimetypes`
modülünün ilk kullanımı Windows'ta `read_windows_registry()` ile HKEY_CLASSES_ROOT'u
taramayı tetikliyor. Donmuş (PyInstaller) bir exe içinde bu tarama kullanıcı
isteğini bloke ediyor.

Tür tahmini kullanıcının kayıt defterine göre DEĞİŞMEMELİ: aynı dosya her makinede
aynı türü vermeli. Bu yüzden açık bir eşleme kullanılır.
"""

from __future__ import annotations

from fusion_cli.appserver.workspace import guess_mime


def test_bilinen_uzantilar_kayit_defterine_sormadan_cozulur():
    assert guess_mime("a.png") == "image/png"
    assert guess_mime("a.svg") == "image/svg+xml"
    assert guess_mime("a.json") == "application/json"
    assert guess_mime("a.md") == "text/markdown"
    assert guess_mime("a.mp3") == "audio/mpeg"
    assert guess_mime("a.pdf") == "application/pdf"


def test_buyuk_harfli_uzanti_da_cozulur():
    assert guess_mime("FOTO.PNG") == "image/png"


def test_bilinmeyen_uzanti_none_doner():
    """Karar çağırana bırakılır: okuma ikiliyse octet-stream, değilse text/plain."""
    assert guess_mime("a.kimbilir") is None
    assert guess_mime("uzantisiz") is None
