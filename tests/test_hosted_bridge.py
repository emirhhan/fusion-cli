"""Connector istemlerini gerçek web oturumuna taşıyan kanal."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fusion_cli.config.models import HostedConnectorConfig, WebSessionConfig
from fusion_cli.mcp_bridge.hosted import HostedRelayError
from fusion_cli.providers import hosted_bridge
from fusion_cli.providers.hosted_bridge import HostedSessionChannel
from fusion_cli.providers.web_session import WebTurn

from .fakes import make_config


def _connector() -> HostedConnectorConfig:
    return HostedConnectorConfig(
        name="MetaAds",
        url="https://mcp.facebook.com/ads",
        provider="claude_web",
        account="main",
        verified=True,
    )


def _session() -> WebSessionConfig:
    return WebSessionConfig(
        model="claude_web/main/auto",
        provider="claude_web",
        account="main",
        transport="browser",
        login_verified=True,
        enabled=True,
    )


class _Tasima:
    """`build_browser_transport` yerine geçer; gelen mesaj listelerini kaydeder."""

    def __init__(self) -> None:
        self.turns: list[tuple[str, ...]] = []

    def __call__(self, session, **_kwargs):
        async def _transport(credential, messages, model):
            del credential, model
            self.turns.append(tuple(message.content for message in messages))
            return WebTurn(text=f"cevap {len(self.turns)}")

        return _transport


@pytest.fixture
def tasima(monkeypatch):
    fake = _Tasima()
    monkeypatch.setattr(hosted_bridge, "build_browser_transport", fake)
    return fake


async def test_oturum_yoksa_anlasilir_hata(tasima):
    """Sağlayıcı oturumu bağlı değilse connector çalışamaz; sebebi görünmeli."""
    kanal = HostedSessionChannel(make_config())

    with pytest.raises(HostedRelayError, match="claude_web"):
        await kanal(_connector(), "merhaba")

    assert tasima.turns == [], "oturum yokken tarayıcıya hiç gidilmemeli"


async def test_ayni_connector_ayni_konusmayi_surdurur(tasima):
    """İlk mesaj SABİT kalmalı: havuz konuşmayı `messages[:1]` ile eşler.

    Her çağrıda yeni bir ilk mesaj göndermek her araç çağrısı için yeni sekme
    açardı — hem yavaş hem connector bağlamı kaybolurdu.
    """
    config = replace(make_config(), web_sessions=(_session(),))
    kanal = HostedSessionChannel(config)

    await kanal(_connector(), "birinci istem")
    await kanal(_connector(), "ikinci istem")

    assert len(tasima.turns) == 2
    assert tasima.turns[0][0] == tasima.turns[1][0]
    # Geçmiş birikir: onarım istemi "önceki cevabın" ne olduğunu bilebilsin.
    assert "birinci istem" in tasima.turns[1]
    assert "cevap 1" in tasima.turns[1]
    assert tasima.turns[1][-1] == "ikinci istem"


async def test_kanal_modelin_metnini_dondurur(tasima):
    config = replace(make_config(), web_sessions=(_session(),))
    kanal = HostedSessionChannel(config)

    cevap = await kanal(_connector(), "istem")

    assert cevap == "cevap 1"


async def test_gecmis_gonderilen_kismi_biriktirmez(tasima):
    """Geçmiş sınırsız büyürse uzun oturumda maliyet N² olur.

    `_deliver_turn` yalnız gönderilmemiş kısmı yazar; gönderilmiş önek
    KORUNMAK zorunda değildir. Ölçülen iki maliyet: sürekli büyüyen `Message`
    listesi ve her çağrıda tüm geçmişi tarayan `_task_reminder`.
    """
    config = replace(make_config(), web_sessions=(_session(),))
    kanal = HostedSessionChannel(config)

    for index in range(6):
        await kanal(_connector(), f"istem {index}")

    # Önsöz + son alışveriş kalır; tarih sınırsız birikmez.
    assert kanal.conversations[("claude_web", "main")] <= 4
    # Önsöz HER ZAMAN ilk mesaj olmalı: havuz konuşmayı onunla eşler.
    assert tasima.turns[-1][0] == tasima.turns[0][0]
