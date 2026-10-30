"""Uzak istemcinin RPC izin listesi (S2-27).

Ölçüldü (30 Ekim): uzak cihaz yalnız `RemoteService._handlers()` yöntemlerini çağırabilir;
masaüstü oturumunun iç yöntemleri (`kontrol.anahtar_goster`, `surec.baslat`, `proje.yaz`,
`oturum.baslat{mod}`) bu listede YOK ve backend de yalnız sabit bir ad kümesini çağırır. Bu test
o sınırı kilitler: biri ileride bir iç yöntemi uzağa açarsa ya da `tasks.create` onay kipini
(`mod`) oturuma aktarırsa düşer.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from fusion_cli.remote.scopes import Scope

from .test_remote_service import Rig

#: Uzaktan ASLA erişilmemesi gereken oturum yöntemleri (masaüstü yüzeyine özgü).
FORBIDDEN_METHODS = (
    "kontrol.anahtar_goster",
    "kontrol.anahtar_kaydet",
    "surec.baslat",
    "surec.durdur",
    "proje.yaz",
    "proje.sil",
    "oturum.baslat",
    "tur.calistir",
    "oturum.mod",
    "uzak.eslestir",
    "uzak.cihaz_sil",
)

#: Uzak servisin açıkça sunduğu yöntemlerin alt kümesi için ön ek denetimi.
FORBIDDEN_PREFIXES = ("kontrol.", "surec.", "proje.", "oturum.", "uzak.", "tur.", "dev.")

ALL_SCOPES = frozenset(item.value for item in Scope)


@pytest.fixture
async def rig(tmp_path: Path) -> AsyncIterator[Rig]:
    instance = Rig(tmp_path)
    yield instance
    instance.backend.release.set()
    await instance.service.aclose()
    await instance.client.aclose()


@pytest.mark.parametrize("method", FORBIDDEN_METHODS)
async def test_en_yuksek_yetkili_cihaz_bile_ic_yontem_cagiramaz(rig: Rig, method: str) -> None:
    phone = rig.registry.add("Tel", "signed", ALL_SCOPES)

    result = await rig.service.call(phone, method, {"mod": "bypass", "komut": "id"})

    assert not result.ok and result.error == "yontem_yok"
    assert rig.backend.calls == []


async def test_sunulan_yontemler_ic_yuzey_on_eki_tasimaz(rig: Rig) -> None:
    exposed = set(rig.service._handlers())

    assert exposed, "uzak servis hiç yöntem sunmuyor olamaz"
    assert not [name for name in exposed if name.startswith(FORBIDDEN_PREFIXES)], exposed


@pytest.mark.parametrize("extra", [{"mod": "bypass"}, {"mode": "bypass"}, {"approval": "bypass"}])
async def test_gorev_olusturma_onay_kipini_oturuma_aktarmaz(
    rig: Rig, extra: dict[str, Any]
) -> None:
    phone = rig.registry.add("Tel", "signed", ALL_SCOPES)

    result = await rig.service.call(phone, "tasks.create", {"prompt": "merhaba", **extra})

    assert result.ok
    options = next(iter(rig.backend.options.values()), {})
    assert not {"mod", "mode", "approval"} & set(options)
    assert all(name != "oturum.baslat" or "mod" not in data for name, data in rig.backend.calls)
