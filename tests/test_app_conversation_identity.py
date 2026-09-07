"""Uygulama asla RASTGELE kimlikle yazmamalı: ulaşılamayan sohbet üretir.

Ölçüldü (kullanıcının diski, 7 Eylül): tek bir proje dosyasında `varsayilan`,
UUID sekme kimlikleri ve otomatik `session-<zaman>-<rastgele>` kimlikleri yan
yana duruyor — 110 sohbetin çoğu bu otomatik kimliklerle yazılmış. Otomatik
kimlik her açılışta değiştiği için o konuşmalara arayüzden bir daha ulaşılamaz.

Otomatik kimlik TUI'nin sözleşmesidir; uygulamanın sekmesi kimliğini bilir.
"""

from __future__ import annotations

import json

import pytest

from fusion_cli.appserver.session import FALLBACK_CONVERSATION_ID, AppSession

pytestmark = pytest.mark.asyncio


async def test_kimlik_bildirilmeden_yazilan_tur_sabit_kimlige_gider(tmp_path):
    """Kimlik gelmeden yazılırsa bile sohbet, ulaşılabilir bir kimlikte durmalı."""
    satirlar: list[str] = []
    oturum = AppSession(satirlar.append, root=tmp_path, home=tmp_path / "ev")

    oturum._transcript_store.record_user("merhaba")

    olaylar = [
        json.loads(satir)
        for satir in (oturum._transcript_store.events_path).read_text(encoding="utf-8").splitlines()
    ]
    assert {olay["session_id"] for olay in olaylar} == {FALLBACK_CONVERSATION_ID}


async def test_sabit_kimlik_rastgele_degil_kararlidir(tmp_path):
    """İki açılış aynı kimliğe yazmalı; aksi halde dünkü sohbet kaybolur."""
    ilk = AppSession([].append, root=tmp_path, home=tmp_path / "ev")
    ikinci = AppSession([].append, root=tmp_path, home=tmp_path / "ev")

    assert ilk._transcript_store.session_id == ikinci._transcript_store.session_id
