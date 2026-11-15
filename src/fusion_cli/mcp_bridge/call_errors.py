"""MCP araç çağrısı hatasını modele okunur, sır içermeyen metne çevirir.

Ölçüldü (29 Ekim): çağrı yolundaki `except Exception` yalnız `type(error).__name__`
döndürüyordu ("MCP aracı hatası (sunucu.araç): McpError"). Uzak sunucunun JSON-RPC
hatası (`Invalid params: 'path' must start with res://`) ve `McpNotConnectedError`'ın
"bağlantı neden yok" mesajı tamamen düşüyor, zayıf model neyi düzelteceğini bilemeyip
aynı çağrıyı tekrarlıyordu (M1-01).
"""

from __future__ import annotations

from mcp.shared.exceptions import McpError

from ..core.redaction import redact

#: Uzak hata metninin modele giden en çok karakteri (sır deseni maskelendikten sonra).
MAX_REMOTE_ERROR_CHARS = 500


def describe_call_error(error: BaseException) -> str:
    """Hatanın modele gösterilecek güvenli ayrıntısı; bilinmeyen tür için yalnız tür adı.

    - `McpError`: uzak sunucunun yazdığı mesaj (JSON-RPC `error.message`) — çözüm önerisi
      genelde oradadır.
    - `RuntimeError` türevi bağlantı hatası (`McpNotConnectedError`): kendi mesajı.
    - Diğer istisnalar: ham metin yol/sır sızdırabilir; yalnız tür adı.
    """
    if isinstance(error, McpError):
        return _clip(error.error.message) or type(error).__name__
    if type(error).__name__ == "McpNotConnectedError":
        return _clip(str(error)) or type(error).__name__
    return type(error).__name__


def _clip(text: str) -> str:
    return redact(" ".join(text.split()))[:MAX_REMOTE_ERROR_CHARS]
