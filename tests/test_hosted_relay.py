"""Sağlayıcı oturumu üzerinden MCP araç köprüsü.

Fusion'ın ajanı `MetaAds__get_campaigns(...)` gibi TİPLİ bir araç görür. Altında
her çağrı şu üç adıma iner: argümanlar kurulur → sağlayıcı oturumuna katı bir
talimat yazılır → modelin kendi MCP çağrısı gerçek işi yapar ve ham JSON geri
gelir. Yani web sağlayıcı bir MCP TAŞIYICISIDIR.

Sınırlayıcı neden düz metin: `core/tool_emulation` içinde ölçülmüş ders —
`<tool_call>` gibi HTML'e benzeyen işaretler, HTML render eden bir kanalda sıkı
temizleyici tarafından ÇOCUKLARIYLA birlikte siliniyor ve mesaj boşalıyordu.
Dönüş yolunda da aynı tuzak geçerlidir.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.config.models import HostedConnectorConfig
from fusion_cli.mcp_bridge.hosted import (
    RESULT_CLOSE,
    RESULT_OPEN,
    HostedConnectorClient,
    HostedRelayError,
    parse_result,
)


def _connector(**extra: object) -> HostedConnectorConfig:
    base = {
        "name": "MetaAds",
        "url": "https://mcp.facebook.com/ads",
        "provider": "claude_web",
        "account": "main",
        "verified": True,
    }
    return HostedConnectorConfig(**{**base, **extra})  # type: ignore[arg-type]


def _zarf(payload: object) -> str:
    return f"Tamam, çağırıyorum.\n{RESULT_OPEN}\n{json.dumps(payload)}\n{RESULT_CLOSE}\n"


class _Oturum:
    """`ask` yerine geçer: gönderilen istemleri kaydeder, sırayla cevap verir."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def __call__(self, connector: HostedConnectorConfig, prompt: str) -> str:
        del connector
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""


# --- zarf ayrıştırma ------------------------------------------------------- #


def test_zarf_kod_bloguyla_sarilmis_olsa_da_cozulur():
    """Model JSON'u kod bloğuna almaya bayılır; bu içeriği bozmamalı."""
    metin = f'{RESULT_OPEN}\n```json\n{{"a": 1}}\n```\n{RESULT_CLOSE}'

    assert parse_result(metin) == {"a": 1}


def test_zarf_yoksa_duz_metin_basari_sayilmaz():
    """Model özetleyip geçerse bu BAŞARI değildir — sessiz yutma yasak."""
    with pytest.raises(HostedRelayError, match="zarf"):
        parse_result("Kampanyaların toplam harcaması 1.240 TL civarında.")


# --- keşif ---------------------------------------------------------------- #


async def test_kesif_araclari_ve_semalarini_getirir():
    oturum = _Oturum(
        _zarf(
            {
                "araclar": [
                    {
                        "ad": "get_campaigns",
                        "aciklama": "Kampanyaları listele",
                        "sema": {"type": "object", "properties": {"hesap": {"type": "string"}}},
                    }
                ]
            }
        )
    )
    client = HostedConnectorClient((_connector(),), ask=oturum)

    tools = await client.list_tools("MetaAds")

    assert [tool.name for tool in tools] == ["get_campaigns"]
    assert tools[0].schema["type"] == "object"
    # İstem connector'ın ADRESİNİ taşımalı: modelin hangi connector'ı
    # kullanacağını tahmin etmesi gerekmez.
    assert "mcp.facebook.com/ads" in oturum.prompts[0]


# --- çağrı ---------------------------------------------------------------- #


async def test_cagri_argumanlari_birebir_gonderir_ve_sonucu_cozer():
    oturum = _Oturum(_zarf({"ok": True, "sonuc": {"kampanya_sayisi": 3}}))
    client = HostedConnectorClient((_connector(),), ask=oturum)

    result = await client.call("MetaAds", "get_campaigns", {"hesap": "act_123"})

    assert result.ok
    assert result.structured == {"kampanya_sayisi": 3}
    assert '"hesap": "act_123"' in oturum.prompts[0]
    assert "get_campaigns" in oturum.prompts[0]


async def test_uzak_hata_basari_sayilmaz():
    """Ölçülmüş ders (mcp_bridge/client.py): `isError` atılırsa model düzeltemez."""
    oturum = _Oturum(_zarf({"ok": False, "hata": "ads_management izni yok"}))
    client = HostedConnectorClient((_connector(),), ask=oturum)

    result = await client.call("MetaAds", "get_campaigns", {})

    assert result.ok is False
    assert "ads_management izni yok" in result.output


async def test_bozuk_zarf_bir_kez_onarilir():
    """Sözleşme onarımı: ilk cevap bozuksa bir kez daha, katı hatırlatmayla istenir."""
    oturum = _Oturum("özet geçtim", _zarf({"ok": True, "sonuc": {"a": 1}}))
    client = HostedConnectorClient((_connector(),), ask=oturum)

    result = await client.call("MetaAds", "get_campaigns", {})

    assert result.ok
    assert len(oturum.prompts) == 2
    assert RESULT_OPEN in oturum.prompts[1]


async def test_iki_kez_bozuk_zarf_gorunur_hata_verir():
    """İkinci denemede de zarf yoksa tur sessizce başarılı sayılmaz."""
    oturum = _Oturum("özet", "yine özet")
    client = HostedConnectorClient((_connector(),), ask=oturum)

    result = await client.call("MetaAds", "get_campaigns", {})

    assert result.ok is False
    assert "zarf" in result.output


# --- kayıt ---------------------------------------------------------------- #


async def test_dogrulanmamis_connector_kaydedilmez():
    from fusion_cli.tools import ToolRegistry

    oturum = _Oturum()
    client = HostedConnectorClient((_connector(verified=False),), ask=oturum)

    eklenen = await client.register_into(ToolRegistry())

    assert eklenen == ()
    assert oturum.prompts == [], "doğrulanmamış connector için oturuma hiç gidilmemeli"


async def test_kayitli_araclar_connector_onekiyle_ve_mutating_gelir():
    from fusion_cli.tools import ToolRegistry

    oturum = _Oturum(
        _zarf({"araclar": [{"ad": "get_campaigns", "aciklama": "listele", "sema": {}}]})
    )
    client = HostedConnectorClient((_connector(),), ask=oturum)
    registry = ToolRegistry()

    eklenen = await client.register_into(registry)

    assert eklenen == ("MetaAds__get_campaigns",)
    arac = registry.get("MetaAds__get_campaigns")
    assert arac is not None
    # Dış aracın ne yaptığı bilinemez: onay akışından geçsin.
    assert arac.mutating is True
