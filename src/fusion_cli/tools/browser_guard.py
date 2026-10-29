"""Tarayıcı bağlamında HER isteği SSRF kapısından geçiren yönlendirici.

Ölçüldü (29 Ekim): `browser_block_reason` yalnız araca verilen İLK adresi denetliyordu.
Dış bir sayfa `302 → http://127.0.0.1:PORT/` (ya da bulut metadata ucu) dönerse, sayfa
`<img>`/`fetch` ile iç adres isterse ya da tıklama sonrası gezinme iç adrese giderse
Chromium oraya gidiyordu. `web_fetch` her sıçramayı denetler; iki araç farklı
güvenlik seviyesindeydi. Burada `context.route` ile bağlamdaki her istek (yönlendirme
sıçraması, alt kaynak, yeni sekme, `location=`) aynı `browser_block_reason` kapısından
geçer; yerel izin listesi `context.local_origins`'in CANLI kümesinden okunur.

Bilinen sınırlar: adı Chromium'un kendi çözümleyicisi çözer, denetim ayrı bir
çözümlemedir (TTL=0 ile yeniden bağlama yarışı kapanmaz; `pinned_http` yalnız httpx
tarafında IP sabitler). WebSocket ve service worker istekleri `route`'a düşmez.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from typing import Any
from urllib.parse import urljoin, urlparse

from ..core.constants import MAX_WEB_REDIRECTS
from .web import browser_block_reason

#: Playwright nesneleri (`core`/RULES gereği playwright burada import edilmez; tip gevşek).
PlaywrightObject = Any
#: Ağa çıkmayan, sayfa içi şemalar: adres denetimi anlamsızdır.
_LOCAL_SCHEMES = frozenset({"data", "blob", "about"})
#: Playwright'ın engellenen istek için döndürdüğü hata kodu.
BLOCKED_ERROR = "blockedbyclient"
#: Çözümleme sonucu önbelleğinin üst sınırı; sayfa başına yüzlerce kaynak olabilir.
_MAX_CACHE = 512


class RequestGuard:
    """Bir tarayıcı bağlamının istek denetçisi (adres → gerekçe önbelleğiyle)."""

    def __init__(self, allowed_local: Collection[str]) -> None:
        #: CANLI küme: kullanıcı tur sırasında yeni yerel adres yazarsa görülür.
        self._allowed_local = allowed_local
        self._cache: dict[tuple[str, str, int | None, frozenset[str]], str | None] = {}
        self.blocked: list[str] = []

    async def reason_for(self, url: str) -> str | None:
        """İstek engellenmeliyse Türkçe gerekçe, geçebilirse None."""
        parsed = urlparse(url)
        if parsed.scheme in _LOCAL_SCHEMES:
            return None
        try:
            port = parsed.port
        except ValueError:
            return "geçersiz port"
        key = (parsed.scheme, (parsed.hostname or "").lower(), port, frozenset(self._allowed_local))
        if key in self._cache:
            return self._cache[key]
        # Ad çözümlemesi bloklar; olay döngüsünü tutmasın.
        reason = await asyncio.to_thread(browser_block_reason, url, self._allowed_local)
        if len(self._cache) >= _MAX_CACHE:
            self._cache.clear()
        self._cache[key] = reason
        return reason

    async def handle(self, route: PlaywrightObject) -> None:
        """`context.route` geri çağırımı: geçenleri sürdür, kalanları iptal et."""
        url = str(route.request.url)
        reason = await self.reason_for(url)
        if reason is not None:
            self.blocked.append(f"{url} ({reason})")
            await route.abort(BLOCKED_ERROR)
            return
        if urlparse(url).scheme in _LOCAL_SCHEMES:
            await route.continue_()
            return
        # `continue_` ile (ve 3xx `fulfill` ile) Chromium yönlendirmeyi KENDİ içinde
        # izler ve sıçrama `route`'a düşmez (ölçüldü: 302 → izinsiz yerel adres
        # denetlenmeden gitti). Bu yüzden istek yönlendirme izlenmeden alınır ve
        # Location zinciri burada elle yürünür; zincirin her adresi kapıdan geçerse
        # yanıt tarayıcıya verilir.
        try:
            response = await route.fetch(max_redirects=0)
            if not await self._redirect_chain_allowed(route, url, response):
                await route.abort(BLOCKED_ERROR)
                return
        except Exception:  # ağ hatası: tarayıcıya hata olarak yansır
            await route.abort("failed")
            return
        await route.fulfill(response=response)

    async def _redirect_chain_allowed(
        self, route: PlaywrightObject, url: str, response: PlaywrightObject
    ) -> bool:
        """3xx zincirindeki HER adres kapıdan geçiyor mu? (`web_fetch` ile aynı sıkılık)"""
        current_url, current = url, response
        for _hop in range(MAX_WEB_REDIRECTS):
            location = current.headers.get("location")
            if not 300 <= current.status < 400 or not location:
                return True
            target = urljoin(current_url, location)
            reason = await self.reason_for(target)
            if reason is not None:
                self.blocked.append(f"{target} ({reason}) — yönlendirme")
                return False
            page_context = route.request.frame.page.context
            current = await page_context.request.get(target, max_redirects=0)
            current_url = target
        return False


async def install_request_guard(
    context: PlaywrightObject, allowed_local: Collection[str]
) -> RequestGuard:
    """Bağlamdaki (açılacak yeni sekmeler dâhil) tüm istekleri denetim altına al."""
    guard = RequestGuard(allowed_local)
    await context.route("**/*", guard.handle)
    return guard


def blocked_hint(exc: Exception) -> str:
    """Gezinme hatası adres kapısından geldiyse kullanıcıya/modele açıklayan ek."""
    if BLOCKED_ERROR.upper() in str(exc).upper().replace("_", ""):
        return (
            " — adres kapısı bir yönlendirmeyi/kaynağı engelledi (iç ağ ya da izinsiz yerel adres)"
        )
    return ""
