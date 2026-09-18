"""Zaman aşımı/iptal sonrası oturum yeni mesaj kabul etmeli.

Ölçüldü (17 Eylül denetimi): tur 15 dakikada cevapsız kalıp iptal edildikten
hemen sonra gönderilen mesaj "Zaten çalışan bir tur var" ile reddedildi ve
kullanıcı bir süre yazamadı.
"""

from __future__ import annotations

import asyncio

from fusion_cli.ui import messages


def test_kilit_mesaji_protokol_adi_icermez() -> None:
    """Kullanıcı `tur.kes` gibi iç protokol adlarını görmemeli."""
    assert "tur.kes" not in messages.APP_TURN_ALREADY_RUNNING
    assert "`" not in messages.APP_TURN_ALREADY_RUNNING


async def test_iptalden_sonra_yeni_tur_kabul_edilir() -> None:
    """İptal edilen tur kapanana kadar kısa süre beklenir, sonra yol açılır."""
    from fusion_cli.appserver import session as oturum_modulu

    class _SahteOturum:
        _iptal_bekliyor = True

        def __init__(self, gorev: asyncio.Task[None]) -> None:
            self._turn = gorev

    async def _uzun_is() -> None:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)  # bırakma payı
            raise

    gorev = asyncio.ensure_future(_uzun_is())
    await asyncio.sleep(0)
    gorev.cancel()
    sahte = _SahteOturum(gorev)

    await oturum_modulu.AppSession._iptal_edilen_turu_bekle(sahte)  # type: ignore[arg-type]

    assert gorev.done()
    assert sahte._iptal_bekliyor is False
