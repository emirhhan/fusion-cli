"""Oturum yeniden kaydedilirken KULLANICI TERCİHLERİ korunmalı.

Ölçüldü (11 Eylül): ChatGPT Cloudflare bot kontrolüne takıldığı için oturumu
görünür kipe almak gerekiyordu (`headless: false`). Kullanıcı arayüzden oturumu
yeniden sınadığında `save_browser_session` oturumu SIFIRDAN kuruyor ve `headless`
alanını taşımıyordu; tercih sessizce `true`ya dönüyor, görünür pencere hiç
açılmıyor ve aynı hata tekrar alınıyordu.

`headless` ve `timeout_s` türetilmiş durum değil, kullanıcının bilinçli seçimidir.
Aynı dosyada `tool_eval_passed` için koruma deseni zaten vardı.
"""

from __future__ import annotations

from dataclasses import replace

from fusion_cli.config.models import WebSessionConfig
from fusion_cli.providers import web_control

from .fakes import make_config


def _session(**extra: object) -> WebSessionConfig:
    base = {
        "model": "chatgpt_web/main/auto",
        "provider": "chatgpt_web",
        "account": "main",
        "transport": "browser",
        "enabled": True,
    }
    return WebSessionConfig(**{**base, **extra})  # type: ignore[arg-type]


def test_gorunur_kip_secimi_yeniden_kayitta_korunur(monkeypatch, tmp_path):
    from fusion_cli.config import writer as writer_module

    monkeypatch.setattr(
        writer_module, "write_web_sessions", lambda config, path=None: tmp_path / "c.yaml"
    )
    config = replace(
        make_config(),
        web_sessions=(_session(headless=False, timeout_s=240.0),),
    )

    yeni, sonuc = web_control.register_session(
        config, "chatgpt_web", "main", tool_support="emulated"
    )

    assert yeni is not None, sonuc
    kayit = next(s for s in yeni.web_sessions if s.provider == "chatgpt_web")
    assert kayit.headless is False, "görünür kip seçimi sıfırlandı"
    assert kayit.timeout_s == 240.0, "tur bütçesi sıfırlandı"


def test_yeni_oturum_varsayilanlarla_gelir(monkeypatch, tmp_path):
    """Mevcut oturum yoksa varsayılan davranış değişmez."""
    from fusion_cli.config import writer as writer_module

    monkeypatch.setattr(
        writer_module, "write_web_sessions", lambda config, path=None: tmp_path / "c.yaml"
    )

    yeni, sonuc = web_control.register_session(
        make_config(), "chatgpt_web", "main", tool_support="emulated"
    )

    assert yeni is not None, sonuc
    kayit = next(s for s in yeni.web_sessions if s.provider == "chatgpt_web")
    assert kayit.headless is True
