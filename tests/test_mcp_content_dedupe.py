"""MCP `structuredContent` aynı veriyi metin bloğunda da taşıyorsa bağlama ikinci kez girmez.

Ölçüldü (30 Ekim): spec gereği çoğu sunucu sonucu hem `content` metni hem
`structuredContent` olarak döndürür; çıktıya iki kez giriyor, bağlam bütçesi boşa
gidiyordu. Boş başarılı sonuç `""` kalıyor, modele hiçbir şey söylemiyordu (M1-28).
"""

from __future__ import annotations

import json

from mcp.types import CallToolResult, TextContent

from fusion_cli.mcp_bridge.content import normalize_call_result


def test_ayni_veri_hem_metinde_hem_structured_ise_tek_kez_girer():
    veri = {"kampanyalar": [1, 2, 3], "toplam": 3}
    sonuc = normalize_call_result(
        CallToolResult(
            content=[TextContent(type="text", text=json.dumps(veri))],
            structuredContent=veri,
        )
    )

    assert sonuc.output.count('"toplam"') == 1
    assert sonuc.structured == veri


def test_farkli_metin_ve_structured_ikisi_de_korunur():
    sonuc = normalize_call_result(
        CallToolResult(
            content=[TextContent(type="text", text="Özet: 3 kampanya")],
            structuredContent={"toplam": 3},
        )
    )

    assert "Özet: 3 kampanya" in sonuc.output
    assert '"toplam": 3' in sonuc.output


def test_bos_basarili_sonuc_modele_bos_oldugunu_soyler():
    sonuc = normalize_call_result(CallToolResult(content=[]))

    assert sonuc.ok is True
    assert "boş" in sonuc.output


def test_bos_hata_sonucu_bos_kalir_cagiran_hata_mesaji_uretir():
    sonuc = normalize_call_result(CallToolResult(content=[], isError=True))

    assert sonuc.ok is False
    assert sonuc.output == ""
