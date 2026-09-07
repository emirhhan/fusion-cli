"""Web'e giriş yapan kullanıcı ÇALIŞIR bir kuruluma sahip olmalı.

Ölçüldü (7 Eylül): kullanıcı Gemini web'e giriş yapıyor, oturum yapılandırmaya
yazılıyor ve panel "bağlı" diyor — ama agent/hakem/aday zincirleri hâlâ API
anahtarı isteyen modelleri gösteriyor ve hazırlık raporu `NOT_READY` diyordu.
Ürünün kimliği ücretsiz modellerle çalışmaktır; giriş yaptıktan sonra
kullanıcının yapılandırmayı elle düzeltmesi beklenemez.

Yönlendirme DAR olmalı: anahtarı olan kullanıcının kurduğu zincir sessizce
değiştirilmemeli.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fusion_cli.config.keys import ProviderKeys
from fusion_cli.config.loader import load_config
from fusion_cli.config.readiness import Readiness, evaluate
from fusion_cli.providers import web_control

VARSAYILAN = Path("src/fusion_cli/config/defaults.yaml")


@pytest.fixture
def izole(tmp_path, monkeypatch):
    """Yazmalar kullanıcının GERÇEK config'ine değil geçici dizine gitsin."""
    yazilan: dict[str, object] = {}
    monkeypatch.setattr(
        "fusion_cli.config.writer.write_web_sessions", lambda c, path=None: tmp_path / "c.yaml"
    )
    monkeypatch.setattr(
        "fusion_cli.config.writer.write_model_section",
        lambda c, path=None: (yazilan.__setitem__("model", c), tmp_path / "c.yaml")[1],
    )
    return yazilan


def _anahtarsiz(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.config.keys.detect", lambda: ProviderKeys(openrouter=False, nim=False)
    )


def _anahtarli(monkeypatch):
    monkeypatch.setattr(
        "fusion_cli.config.keys.detect", lambda: ProviderKeys(openrouter=True, nim=True)
    )


def test_anahtarsiz_kullanicida_roller_web_oturumuna_baglanir(izole, monkeypatch):
    _anahtarsiz(monkeypatch)
    config = load_config(VARSAYILAN)
    assert evaluate(config, ProviderKeys(False, False)).state is Readiness.NOT_READY

    yeni, mesaj = web_control.register_session(config, "gemini_web", "main")

    assert mesaj["ok"]
    assert yeni.agent.models[0] == "gemini_web/main/auto"
    assert yeni.judge.models[0] == "gemini_web/main/auto"
    assert yeni.candidates[0].models[0] == "gemini_web/main/auto"


def test_eski_modeller_yedek_olarak_kalir(izole, monkeypatch):
    """Kullanıcı sonradan anahtar eklerse zincir çalışmaya devam etmeli."""
    _anahtarsiz(monkeypatch)
    config = load_config(VARSAYILAN)
    onceki = config.agent.models[0]

    yeni, _ = web_control.register_session(config, "gemini_web", "main")

    assert onceki in yeni.agent.models[1:]


def test_calisan_kurulumu_olan_kullanicinin_zinciri_degismez(izole, monkeypatch):
    """Yönlendirme yalnız HİÇBİR rol çalışmıyorken yapılır."""
    _anahtarli(monkeypatch)
    config = load_config(VARSAYILAN)

    yeni, _ = web_control.register_session(config, "gemini_web", "main")

    assert yeni.agent.models[0] == config.agent.models[0]
    assert "model" not in izole, "çalışan kurulumda model bölümü yazılmamalı"
