"""#436: masaüstü sohbetinde /clear ve sohbet değişince Chrome oturum sekme grubu kapanışı."""

from __future__ import annotations

import asyncio

from fusion_cli.appserver.protocol import Request
from fusion_cli.appserver.session import AppSession


class _Kopru:
    def __init__(self) -> None:
        self.closes: list[bool] = []

    async def close_tab_group(self, *, only_empty: bool) -> int:
        self.closes.append(only_empty)
        return 1


def _oturum(tmp_path) -> tuple[AppSession, _Kopru]:
    oturum = AppSession([].append, root=tmp_path, home=tmp_path / "ev")
    kopru = _Kopru()
    oturum._chrome = kopru  # type: ignore[assignment]
    return oturum, kopru


async def _bekle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def test_clear_grubu_sayfalariyla_kapatir(tmp_path):
    oturum, kopru = _oturum(tmp_path)
    await oturum.handle(Request("1", "komut.calistir", {"ad": "clear", "arguman": ""}))
    await _bekle()
    assert kopru.closes == [False]


async def test_sohbet_degisince_grup_yalniz_bossa_kapanir(tmp_path):
    oturum, kopru = _oturum(tmp_path)
    await oturum.handle(Request("1", "oturum.baslat", {"sohbet_id": "a"}))
    await _bekle()
    kopru.closes.clear()
    await oturum.handle(Request("2", "oturum.baslat", {"sohbet_id": "a"}))
    await _bekle()
    assert kopru.closes == []
    await oturum.handle(Request("3", "oturum.baslat", {"sohbet_id": "b"}))
    await _bekle()
    assert kopru.closes == [True]


async def test_kopru_yoksa_hicbir_sey_yapmaz():
    from fusion_cli.appserver.chrome_group import schedule_group_close

    schedule_group_close(None, only_empty=False)
