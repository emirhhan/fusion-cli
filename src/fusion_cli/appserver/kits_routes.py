"""Masaüstünün Kits gelen kutusu RPC'leri: `kit.listele`, `kit.gonder`, `kit.durum`.

Araçlarla (`tools/kits.py`) aynı istemciyi kullanır; ikinci bir yol açmaz. İstek verisi
Türkçe anahtarlıdır (`kit`, `metin`, `baslik`, `tur`, `gorev_id`), yanıt `{ok, ...}`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..tools.kits import KINDS, KitsClient, KitsError, validate_text

KITS_ROUTES = frozenset({"kit.listele", "kit.gonder", "kit.durum"})

#: `kit.gonder` ile gönderilebilen tür adları (Türkçe).
_KIND_NAMES = frozenset({"gorev", "mesaj"})


def _text(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


async def dispatch_kits(
    name: str,
    data: Mapping[str, object],
    client_factory: Callable[[], KitsClient] = KitsClient,
) -> dict[str, Any]:
    """Tek giriş: ad bilinmiyorsa ya da Kits ulaşılmazsa `ok: False` ve Türkçe `metin`."""
    if name not in KITS_ROUTES:
        return {"ok": False, "metin": "Bilinmeyen Kits isteği."}
    try:
        client = client_factory()
        if name == "kit.listele":
            return {"ok": True, "kitler": await client.list_kits(), "adres": client.endpoint.url}
        kit = _text(data, "kit")
        if not kit:
            return {"ok": False, "metin": "Bir Kit adı ya da kimliği gir."}
        if name == "kit.gonder":
            metin = data.get("metin")
            if not isinstance(metin, str):
                return {"ok": False, "metin": "Gönderilecek metni yaz."}
            reason = validate_text(metin)
            if reason is not None:
                return {"ok": False, "metin": reason}
            tur = _text(data, "tur") or "gorev"
            if tur not in _KIND_NAMES:
                return {"ok": False, "metin": "Tür 'gorev' ya da 'mesaj' olmalı."}
            receipt = await client.send(
                kit, metin, title=_text(data, "baslik") or None, kind=KINDS[tur]
            )
            return {"ok": True, **receipt}
        gorev = _text(data, "gorev_id")
        if gorev:
            return {"ok": True, **await client.status(kit, gorev)}
        return {"ok": True, "kayitlar": await client.inbox(kit)}
    except KitsError as error:
        return {"ok": False, "metin": str(error)}
