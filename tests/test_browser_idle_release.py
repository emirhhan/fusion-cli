"""Boşta kalan paylaşılan Chrome'un bırakılması.

Ölçüldü (26 Eylül): Fusion açık kaldıkça gizli Chrome da açık kalıyordu. macOS
aynı uygulamanın çalışan kopyasını öne getirdiği için kullanıcı Dock'taki
Chrome'a tıklayınca kendi Chrome'u açılmıyor, eklentilerini göremiyordu.
"""

from __future__ import annotations

import asyncio

from fusion_cli.providers.web_browser import BrowserSessionPool, ConversationState


class _Sayfa:
    def __init__(self) -> None:
        self.kapali = False

    def is_closed(self) -> bool:
        return self.kapali

    async def close(self) -> None:
        self.kapali = True


async def test_bosta_kalan_oturum_birakilir():
    havuz = BrowserSessionPool(idle_release_s=0.05)
    havuz._contexts[("gemini_web", "main")] = object()
    havuz.remember_conversation("gemini_web", "main", "kok", ConversationState(page=_Sayfa()))

    havuz.schedule_idle_release("gemini_web", "main")
    await asyncio.sleep(0.2)

    assert ("gemini_web", "main") not in havuz._contexts
    assert havuz.conversation("gemini_web", "main", "kok") is None


async def test_kullanim_surerken_birakilmaz_ve_sure_yenilenir():
    havuz = BrowserSessionPool(idle_release_s=0.1)
    havuz._contexts[("gemini_web", "main")] = object()

    async with havuz.lock_for("gemini_web", "main"):
        havuz.schedule_idle_release("gemini_web", "main")
        await asyncio.sleep(0.25)
        assert ("gemini_web", "main") in havuz._contexts
    havuz.schedule_idle_release("gemini_web", "main")
    await asyncio.sleep(0.05)
    havuz.schedule_idle_release("gemini_web", "main")  # yeni kullanım süreyi sıfırlar
    await asyncio.sleep(0.06)
    assert ("gemini_web", "main") in havuz._contexts
    await asyncio.sleep(0.2)
    assert ("gemini_web", "main") not in havuz._contexts


async def test_birakma_gorevi_tutulur_ve_birakma_boyunca_hesap_kilidi_alinir():
    """Ölçüldü (30 Ekim): (1) `create_task` sonucu referanssız (asyncio zayıf referans tutar,
    görev toplanabilir); (2) kilit yalnız bakılıp bırakılıyor, `await` sırasında başka tur
    kilidi alırsa bağlam tur ortasında kapanıyordu (P1-27)."""
    havuz = BrowserSessionPool(idle_release_s=0.01)
    havuz._contexts[("gemini_web", "main")] = object()
    kilitli_mi: list[bool] = []

    async def yavas_birak(provider: str, account: str) -> None:
        kilitli_mi.append(havuz.lock_for(provider, account).locked())
        await asyncio.sleep(0.05)

    havuz.drop_account_conversations = yavas_birak  # type: ignore[method-assign]

    havuz.schedule_idle_release("gemini_web", "main")
    await asyncio.sleep(0.03)

    assert havuz._background_tasks, "görev referansı tutulmalı"
    assert kilitli_mi == [True], "bırakma kilit altında yapılmalı"
    await asyncio.sleep(0.2)
    assert not havuz._background_tasks
