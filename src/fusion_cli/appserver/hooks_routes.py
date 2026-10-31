"""Masaüstü `kanca.*` istekleri (P-009): Ayarlar › İzinler'deki kanca listesi.

    kanca.listele   {kancalar: [{olay, eslestirici, komut, sure_sn, kaynak, dosya, atlandi}],
                     kapali, guvensiz_katmanlar, kullanici_dosyasi}

Liste salt okunurdur (Claude Code `/hooks` gibi); düzenleme dosyada yapılır. Tanımlar
istek anında dosyadan okunur: güven verildikten sonra liste hemen güncellenir.
"""

from __future__ import annotations

from typing import Any

from ..config.hooks import hook_rows, user_hooks_file
from ..engines.hooks.session import HookSession

HOOK_ROUTES = frozenset({"kanca.listele"})


def dispatch_hooks(name: str, session: HookSession) -> dict[str, Any]:
    if name != "kanca.listele":
        return {"ok": False, "metin": "Bilinmeyen kanca isteği."}
    hooks = session.loader()
    return {
        "ok": True,
        "kancalar": [
            {
                "olay": row.event,
                "eslestirici": row.matcher,
                "komut": row.command,
                "sure_sn": row.timeout_s,
                "kaynak": row.source,
                "dosya": row.path,
                "atlandi": row.skipped,
            }
            for row in hook_rows(hooks)
        ],
        "kapali": hooks.disabled_reason,
        "guvensiz_katmanlar": list(hooks.untrusted_layers),
        "kullanici_dosyasi": str(user_hooks_file()),
    }
