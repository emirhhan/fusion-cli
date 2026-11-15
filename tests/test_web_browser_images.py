"""Tarayıcı web oturumunda görsel yolu (P1-06).

Ölçüldü (29 Ekim): `supports_images=session.transport != "browser"` tarayıcıda hep
False; `_prepare_images` görseli `Message` kopyasında düşürüyor ve `pending_images` boş
kalıyordu. `_attach_images` (Gemini'ye yükleme) çalışma yolundan düşmüştü.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.core.types import Message
from fusion_cli.providers.capabilities import capabilities_for
from fusion_cli.providers.web_browser import image_upload_notice, pending_images
from fusion_cli.providers.web_registry import WebSessionRegistry

_GORSEL = "data:image/png;base64,aGVsbG8="


def _oturum(saglayici: str) -> WebSessionConfig:
    return WebSessionConfig(
        model=f"{saglayici}/main/auto",
        provider=saglayici,
        account="main",
        transport="browser",
        tool_support="emulated",
    )


def _adaptor(saglayici: str):
    oturum = _oturum(saglayici)
    return WebSessionRegistry((oturum,), environ={}).build_session(oturum)


def test_gemini_tarayici_oturumu_gorseli_dusurmez():
    mesaj = Message("user", "bak", images=(_GORSEL,))

    hazir = _adaptor("gemini_web")._prepare_images(mesaj)

    assert pending_images((hazir,)) == (_GORSEL,)
    assert "incelenmedi" not in hazir.content


def test_gorsel_yolu_olmayan_tarayici_saglayicisi_gorseli_acikca_dusurur():
    mesaj = Message("user", "bak", images=(_GORSEL,))

    hazir = _adaptor("chatgpt_web")._prepare_images(mesaj)

    assert pending_images((hazir,)) == ()
    assert "görsel incelenmedi" in hazir.content


def test_yetenek_profili_gemini_tarayicida_gorsel_bildirir():
    from fusion_cli.core.types import ModelSpec

    def profil(saglayici: str):
        oturum = replace(_oturum(saglayici), enabled=True)
        return capabilities_for(ModelSpec(name="m", model=oturum.model), (oturum,))

    assert profil("gemini_web").images is True
    assert profil("chatgpt_web").images is False


def test_yukleme_bildirimi_eksik_gorseli_soyler():
    assert image_upload_notice(2, 2).count("yüklenemedi") == 0
    assert "2 görsel ekte" in image_upload_notice(2, 2)
    assert "1 görsel yüklenemedi" in image_upload_notice(1, 2)
    assert "2 görsel yüklenemedi" in image_upload_notice(0, 2)
    assert image_upload_notice(0, 0) == ""
