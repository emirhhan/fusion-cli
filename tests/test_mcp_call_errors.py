"""MCP çağrı hatası modele okunur gelir (M1-01).

Ölçüldü (29 Ekim): `McpError` ve `McpNotConnectedError` mesajı düşüyor, model yalnız
"McpError" görüyordu.
"""

from __future__ import annotations

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData

from fusion_cli.mcp_bridge.call_errors import MAX_REMOTE_ERROR_CHARS
from fusion_cli.mcp_bridge.client import McpClient, McpNotConnectedError


class _HataFirlatanOturum:
    def __init__(self, hata: Exception) -> None:
        self._hata = hata

    async def call_tool(self, name, args):
        raise self._hata


async def _calistir(hata: Exception):
    client = McpClient(())
    client._sessions["godot"] = _HataFirlatanOturum(hata)
    return await client._make_run("godot", "open_scene")({"path": "x"}, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_uzak_json_rpc_hatasinin_mesaji_modele_gider():
    sonuc = await _calistir(
        McpError(ErrorData(code=-32602, message="Invalid params: 'path' must start with res://"))
    )

    assert sonuc.ok is False
    assert "'path' must start with res://" in sonuc.output


@pytest.mark.asyncio
async def test_uzak_hata_mesajindaki_sir_maskelenir_ve_kisaltilir():
    uzun = "token=SENTINELSECRET123 " + "x" * 2000
    sonuc = await _calistir(McpError(ErrorData(code=-1, message=uzun)))

    assert "SENTINELSECRET123" not in sonuc.output
    assert len(sonuc.output) < MAX_REMOTE_ERROR_CHARS + 200


@pytest.mark.asyncio
async def test_baglanti_yok_hatasi_nedenini_soyler():
    sonuc = await _calistir(
        McpNotConnectedError("MCP sunucusuna bağlantı yok: godot. npx bulunamadı.")
    )

    assert "npx bulunamadı" in sonuc.output


@pytest.mark.asyncio
async def test_bilinmeyen_istisnanin_ham_metni_modele_gitmez():
    sonuc = await _calistir(ValueError("/Users/gizli/yol/dosya.txt"))

    assert "ValueError" in sonuc.output
    assert "/Users/gizli" not in sonuc.output
