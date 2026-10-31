"""`type: "http"` kancası (P-009): olay JSON'unu POST eder, yanıtı komut çıktısı gibi okur.

Claude Code'un HTTP kancası sözleşmesi:

    2xx         gövde stdout gibi okunur (boş = karar yok; JSON = karar alanları)
    diğer       engellemeyen hata (3xx yönlendirme izlenmez); engellemek için 2xx + JSON
    bağlantı    hatası / zaman aşımı → engellemeyen hata

Başlık değerlerindeki `$AD` / `${AD}` yalnız `allowedEnvVars` listesindeki adlardan
doldurulur; listede olmayan ad boş metne döner (sır sızmasın). İç ağ koruması: adres bir
kez çözülür ve bütün IP'ler genel internette değilse istek gönderilmez (`pinned_http`,
DNS rebinding dahil); yerel sunucuya (localhost, 192.168.x) istek için kullanıcı
`runtime.hook_http_allow_private: true` yazar — güvenilmeyen proje config'i açamaz.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

import httpx

from ...core.hooks.events import HookCommand, HookRun
from ...tools.pinned_http import AsyncPinnedTransport, BlockedAddressError
from .runner import HOOK_STREAM_CHARS

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
#: 2xx dışı yanıtta hata metnine eklenen gövde kuyruğu.
_ERROR_BODY_CHARS = 300


def expand_header(value: str, allowed: tuple[str, ...], environment: Mapping[str, str]) -> str:
    """`$AD`/`${AD}` yerine izinli ortam değeri; izinsiz ya da tanımsız ad boş metin."""

    def _value(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return environment.get(name, "") if name in allowed else ""

    return _ENV_REFERENCE.sub(_value, value)


async def run_http_hook(
    command: HookCommand,
    payload: Mapping[str, object],
    *,
    environment: Mapping[str, str],
    allow_private: bool = False,
) -> HookRun:
    """İsteği gönder; sonuç hiçbir zaman istisna olarak fırlatılmaz (iptal hariç)."""
    headers = {
        name: expand_header(value, command.allowed_env_vars, environment)
        for name, value in command.headers
    }
    headers.setdefault("Content-Type", "application/json")
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    transport = AsyncPinnedTransport(allows_private=lambda _url: allow_private)
    try:
        async with httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(command.timeout_s), follow_redirects=False
        ) as client:
            response = await client.post(command.command, content=body, headers=headers)
    except httpx.TimeoutException:
        return HookRun(command, None, timed_out=True)
    except BlockedAddressError as error:
        return HookRun(command, None, error=f"{error} (runtime.hook_http_allow_private)")
    except httpx.HTTPError as error:
        return HookRun(command, None, error=f"{type(error).__name__}: {error}"[:_ERROR_BODY_CHARS])
    text = response.text[:HOOK_STREAM_CHARS]
    if not response.is_success:
        tail = f": {text.strip()[:_ERROR_BODY_CHARS]}" if text.strip() else ""
        return HookRun(command, None, error=f"HTTP {response.status_code}{tail}")
    return HookRun(command, 0, text)
