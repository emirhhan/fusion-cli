"""WordPress MCP adaptörü: tek `execute-ability` aracının çağrı bazlı etkisi.

Ölçüldü (26 Eylül, Motogate/Novamira): sunucu 63 yeteneği TEK bir
`mcp-adapter-execute-ability` aracından çalıştırıyor ve o aracın işareti
`destructiveHint=True`. Etki araçtan okunursa otomatik kip ürün aramayı bile
soruyor, plan kipi okumayı engelliyordu. Her yeteneğin kendi işareti
`get-ability-info` çıktısındaki `meta.annotations` içindedir.
"""

from __future__ import annotations

import pytest

from fusion_cli.core.tools import ToolEffect
from fusion_cli.mcp_bridge.ability_effects import ability_gateway_resolver, effect_from_ability_meta


@pytest.mark.parametrize(
    ("annotations", "effect"),
    [
        ({"readonly": True, "destructive": False}, ToolEffect.REMOTE_READ),
        ({"readonly": False, "destructive": True}, ToolEffect.REMOTE_DESTRUCTIVE),
        ({"readonly": False, "destructive": False}, ToolEffect.REMOTE_WRITE),
    ],
)
def test_yetenek_isareti_etkiye_cevrilir(annotations, effect):
    assert effect_from_ability_meta({"meta": {"annotations": annotations}}) is effect


def test_isaretsiz_yetenek_bilinmez_sayilir():
    assert effect_from_ability_meta({"name": "x"}) is None
    assert effect_from_ability_meta(None) is None


async def test_cozucu_yetenegi_bir_kez_sorar_ve_onbellege_alir():
    sorulan: list[str] = []

    async def bilgi(ad: str):
        sorulan.append(ad)
        return {"meta": {"annotations": {"readonly": ad.endswith("query")}}}

    cozucu = ability_gateway_resolver(bilgi)

    assert await cozucu({"ability_name": "woocommerce/products-query"}) is ToolEffect.REMOTE_READ
    assert await cozucu({"ability_name": "woocommerce/products-query"}) is ToolEffect.REMOTE_READ
    assert await cozucu({"ability_name": "woocommerce/product-update"}) is ToolEffect.REMOTE_WRITE
    assert sorulan == ["woocommerce/products-query", "woocommerce/product-update"]


async def test_cozucu_hata_ya_da_eksik_adda_karari_araca_birakir():
    async def bozuk(_ad: str):
        raise RuntimeError("ağ yok")

    cozucu = ability_gateway_resolver(bozuk)
    assert await cozucu({"ability_name": "x"}) is None
    assert await cozucu({}) is None
