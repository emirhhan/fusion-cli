"""Koşu sonu kaynak temizliği: tarayıcı bağlamları ve MCP bağlantıları."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import TypeVar

T = TypeVar("T")

_logger = logging.getLogger(__name__)


async def with_web_cleanup(coro: Awaitable[T]) -> T:
    """İşi çalıştır, bitince tarayıcı bağlamlarını AYNI döngüde kapat.

    Kapatma neden burada: Playwright nesneleri oluşturuldukları event loop'a
    bağlıdır. Temizliği ayrı bir `asyncio.run` ile çağırmak sessizce başarısız
    oluyordu — ölçüldü, koşu bittiği hâlde profili tutan 11 headless Chrome süreci
    kalıyordu ve bunlar `fusion serve`'ün kapanmasını da engelliyordu.

    Tur İÇİNDE kapatılmaz: REPL turlar arası sohbet sürekliliğini bu bağlamlarda
    taşır ve tek bir `asyncio.run` içinde çalışır.

    İki kapatma BİRBİRİNDEN yalıtılır. Ölçüldü (30 Ekim): ilk `await` fırlatınca
    ikincisi hiç çalışmıyor (tarayıcı süreçleri sızıyor) ve işin asıl istisnası
    temizlik hatasıyla maskeleniyordu; hatalar yalnız loglanır.
    """
    from ..mcp_bridge import pool
    from ..providers import web_browser

    try:
        return await coro
    finally:
        # MCP bağlantıları da oturum kaynağıdır: stdio alt süreçleri (npx ...)
        # kapanışta sahipsiz kalmamalı.
        for kapat in (pool.close_mcp_pool, web_browser.close_all_browser_sessions):
            try:
                await kapat()
            except Exception:
                _logger.warning("Koşu sonu temizliği başarısız: %s", kapat.__name__, exc_info=True)
