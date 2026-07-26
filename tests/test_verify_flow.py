"""`/verify` akışı — keşfet, onaylat, kalıcılaştır.

Seçim ekranı enjekte edilir; gerçek terminal gerekmez.
"""

from __future__ import annotations

import pytest

from fusion_cli.cli.repl import verify_flow
from fusion_cli.config.loader import load_config
from fusion_cli.ui import messages


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Kullanıcı dosyası tmp_path'e düşen taze bir yapılandırma."""
    monkeypatch.setattr(
        "fusion_cli.config.writer._target_path", lambda cfg: tmp_path / "config.yaml"
    )
    return load_config()


def _picker(secim):
    """Verilen değeri döndüren sahte seçim ekranı."""

    def _pick(choices, *, title, **kwargs):
        _pick.title = title
        return secim

    return _pick


def test_plan_bulunamazsa_yonlendirme_doner(config, tmp_path):
    sonuc = verify_flow.choose_verification(
        config, tmp_path, picker=_picker("evet"), discover=lambda root: ()
    )

    assert sonuc.message == messages.VERIFY_NOTHING_FOUND
    assert sonuc.config.runtime.verification_commands == ()


def test_onay_verilince_kapi_acilir_ve_yazilir(config, tmp_path):
    plan = ("ruff check .", "pytest -q")

    sonuc = verify_flow.choose_verification(
        config, tmp_path, picker=_picker("evet"), discover=lambda root: plan
    )

    assert sonuc.config.runtime.verification_commands == plan
    assert "ruff check ." in sonuc.message
    assert (tmp_path / "config.yaml").exists(), "onaylanan plan kalıcılaşmalı"


def test_vazgecilirse_hicbir_sey_degismez(config, tmp_path):
    sonuc = verify_flow.choose_verification(
        config, tmp_path, picker=_picker("hayir"), discover=lambda root: ("pytest -q",)
    )

    assert sonuc.message == messages.PICKER_CANCELLED
    assert sonuc.config.runtime.verification_commands == ()
    assert not (tmp_path / "config.yaml").exists(), "vazgeçilen plan yazılmamalı"


def test_esc_ile_cikis_da_vazgecmedir(config, tmp_path):
    sonuc = verify_flow.choose_verification(
        config, tmp_path, picker=_picker(None), discover=lambda root: ("pytest -q",)
    )

    assert sonuc.config.runtime.verification_commands == ()


def test_plan_onaydan_once_ekranda_gosterilir(config, tmp_path):
    """Kullanıcı ne onayladığını GÖRMELİ; keşif tahmindir, sessizce açılmaz."""
    secici = _picker("hayir")

    verify_flow.choose_verification(
        config, tmp_path, picker=secici, discover=lambda root: ("go test ./...",)
    )

    assert "go test ./..." in secici.title


def test_kurulu_kapi_kesif_tahminiyle_ezilmez(config, tmp_path):
    """Kullanıcının kendi yazdığı komutlar korunur."""
    from dataclasses import replace

    mevcut = replace(config, runtime=replace(config.runtime, verification_commands=("make check",)))

    def _cagrilmamali(root):  # pragma: no cover - çağrılırsa test zaten düşer
        raise AssertionError("kurulu kapıda keşif yapılmamalı")

    sonuc = verify_flow.choose_verification(
        mevcut, tmp_path, picker=_picker("evet"), discover=_cagrilmamali
    )

    assert sonuc.config.runtime.verification_commands == ("make check",)
    assert "make check" in sonuc.message
