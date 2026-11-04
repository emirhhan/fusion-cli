"""Panelde motor site izinlerinin kapsamını listele ve aynı yerden geri al."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import browser_sites
from ..engines.agent.approval import ApprovalMemory
from ..engines.agent.chrome_site_approval import BUILTIN_KEY_PREFIX, SITE_KEY_PREFIX


@dataclass(frozen=True)
class SitePermission:
    key: str
    host: str
    scope: str

    def payload(self) -> dict[str, str]:
        return {"anahtar": self.key, "site": self.host, "kapsam": self.scope}


async def site_permission_settings(
    memory: ApprovalMemory,
    revoke: object = None,
) -> dict[str, object]:
    """Chrome oturum ve yerleşik Browser kalıcı izinleri birbirinden ayrılır."""
    if revoke is not None:
        if not isinstance(revoke, str) or not revoke.startswith(
            (SITE_KEY_PREFIX, BUILTIN_KEY_PREFIX)
        ):
            return {"ok": False, "metin": "Geri alınacak site izni geçersiz."}
        if revoke.startswith(BUILTIN_KEY_PREFIX):
            try:
                await asyncio.to_thread(
                    browser_sites.remove_allowed, revoke.removeprefix(BUILTIN_KEY_PREFIX)
                )
            except OSError:
                return {"ok": False, "metin": "Kalıcı site izni kaydedilemedi; yeniden dene."}
        memory.forget(revoke)
    persistent = await asyncio.to_thread(browser_sites.load_allowed)
    rows = [
        SitePermission(scope, scope.removeprefix(SITE_KEY_PREFIX), "Bu oturum boyunca")
        for scope in memory.scopes_with_prefix(SITE_KEY_PREFIX)
    ]
    builtin = set(memory.scopes_with_prefix(BUILTIN_KEY_PREFIX)) | {
        f"{BUILTIN_KEY_PREFIX}{host}" for host in persistent
    }
    rows.extend(
        SitePermission(
            scope,
            scope.removeprefix(BUILTIN_KEY_PREFIX),
            "Kalıcı · yerleşik Browser"
            if scope.removeprefix(BUILTIN_KEY_PREFIX) in persistent
            else "Bu oturum boyunca · yerleşik Browser",
        )
        for scope in sorted(builtin)
    )
    return {"ok": True, "izinler": [row.payload() for row in rows]}
