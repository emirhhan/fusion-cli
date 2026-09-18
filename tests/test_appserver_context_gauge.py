"""Kullanıcı kalan bağlamı görebilmeli.

Claude'da kalan bağlam görünür; Fusion'da yalnız `/cost` komutu vardı ve sohbet
sessizce sıkıştırılıyordu. Ölçüldü (17 Eylül denetimi): uzun oturumda bağlam
91 mesajdan 13'e indi ve kullanıcı bunu yalnız cevabın bozulmasından anladı.
"""

from __future__ import annotations

from fusion_cli.appserver.context_gauge import baglam_olcusu
from fusion_cli.core.types import Message


def test_web_modelinde_dar_esik_kullanilir() -> None:
    gecmis = [Message("user", "x" * 12_000)]

    olcu = baglam_olcusu(gecmis, web=True)

    assert olcu["sinir"] == 24_000
    assert olcu["yuzde"] == 50


def test_api_modelinde_genis_esik_kullanilir() -> None:
    gecmis = [Message("user", "x" * 17_700)]

    olcu = baglam_olcusu(gecmis, web=False)

    assert olcu["sinir"] == 177_000
    assert olcu["yuzde"] == 10


def test_bos_gecmis_sifir_doner() -> None:
    assert baglam_olcusu([], web=True)["yuzde"] == 0


def test_yuzde_yuzu_asamaz() -> None:
    """Eşik aşıldıysa gösterge %100'de durur; sıkıştırma zaten devreye girer."""
    olcu = baglam_olcusu([Message("user", "x" * 90_000)], web=True)

    assert olcu["yuzde"] == 100
    assert olcu["kullanilan"] == 90_000
