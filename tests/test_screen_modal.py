"""Tam-ekran kabuk — onay/soru modal altyapısı."""

from __future__ import annotations

import asyncio


def test_ask_confirm_future_ile_cozulur():
    from fusion_cli.cli.repl.screen import FusionScreen

    async def senaryo() -> None:
        ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
        gorev = asyncio.ensure_future(ekran.ask_confirm("rm -rf /x", danger="yıkıcı"))
        await asyncio.sleep(0)  # ask_confirm modalı kursun

        assert ekran._modal_kind == "confirm"
        assert ekran._modal_danger == "yıkıcı"

        ekran._resolve_confirm(True)
        sonuc = await gorev

        assert sonuc is True
        assert ekran._modal_kind is None  # modal kapandı

    asyncio.run(senaryo())


def test_ask_confirm_reddedilebilir():
    from fusion_cli.cli.repl.screen import FusionScreen

    async def senaryo() -> None:
        ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
        gorev = asyncio.ensure_future(ekran.ask_confirm("tehlikeli komut"))
        await asyncio.sleep(0)
        ekran._resolve_confirm(False)
        assert await gorev is False

    asyncio.run(senaryo())


def test_ask_text_girilen_metni_dondurur():
    from fusion_cli.cli.repl.screen import FusionScreen

    async def senaryo() -> None:
        ekran = FusionScreen(banner="✦ fusion", on_submit=lambda s: None)
        gorev = asyncio.ensure_future(ekran.ask_text("hangi dosya?"))
        await asyncio.sleep(0)

        assert ekran._modal_kind == "text"

        ekran._resolve_text("main.py")
        assert await gorev == "main.py"
        assert ekran._modal_kind is None

    asyncio.run(senaryo())
