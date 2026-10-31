"""Masaüstü `kanca.*` istekleri (P-009): Ayarlar › İzinler'deki kanca listesi.

    kanca.listele   {kancalar: [{olay, eslestirici, komut, sure_sn, kaynak, dosya, atlandi}],
                     kapali, guvensiz_katmanlar, yok_sayilan_kapatma, kullanici_dosyasi,
                     etkin, claude_kancalari}
    kanca.ayar      {anahtar: hooks_enabled|claude_hooks, deger: bool} → kullanıcı config.yaml

Liste salt okunurdur (Claude Code `/hooks` gibi); tanım düzenlemesi dosyada yapılır. İki
anahtar (tüm kancalar, Claude kullanıcı kancaları) masaüstünden açılıp kapatılır; açık
oturumda bir sonraki turda etkilidir. Tanımlar istek anında dosyadan okunur: güven
verildikten sonra liste hemen güncellenir.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..config.hooks import hook_rows, user_hooks_file
from ..config.models import Config
from ..config.settings_access import write_setting
from ..core.errors import FusionError
from ..engines.hooks.session import HookSession
from ..ui import messages

HOOK_ROUTES = frozenset({"kanca.listele", "kanca.ayar"})
#: Masaüstünden değiştirilebilen `runtime` anahtarları.
HOOK_FLAGS = frozenset({"hooks_enabled", "claude_hooks"})


class HookState(Protocol):
    """`ReplState`'in burada kullanılan yüzü."""

    config: Config

    def hooks(self) -> HookSession: ...


def dispatch_hooks(
    name: str, state: HookState, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    if name == "kanca.listele":
        return _list(state)
    if name == "kanca.ayar":
        return _set_flag(state, data or {})
    return {"ok": False, "metin": "Bilinmeyen kanca isteği."}


def _list(state: HookState) -> dict[str, Any]:
    hooks = state.hooks().loader()
    runtime = state.config.runtime
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
        "yok_sayilan_kapatma": list(hooks.ignored_disable_layers),
        "kullanici_dosyasi": str(user_hooks_file()),
        "etkin": runtime.hooks_enabled,
        "claude_kancalari": runtime.claude_hooks,
    }


def _set_flag(state: HookState, data: dict[str, Any]) -> dict[str, Any]:
    key = str(data.get("anahtar", ""))
    value = data.get("deger")
    if key not in HOOK_FLAGS or not isinstance(value, bool):
        return {"ok": False, "metin": messages.HOOKS_FLAG_INVALID}
    try:
        updated, _ = write_setting(state.config, f"runtime.{key}", "true" if value else "false")
    except (FusionError, OSError) as error:
        return {"ok": False, "metin": messages.HOOKS_FLAG_FAILED.format(error=error)}
    state.config = updated
    return {**_list(state), "anahtar": key, "deger": value}
